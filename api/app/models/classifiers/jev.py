"""Classificador local estilo "Jev": decide entre poucas opções olhando o
logprob do token de uma letra-rótulo (A/B/C...), sem gerar texto livre e sem
depender de JSON estruturado.

Por que letras e não as palavras reais: uma palavra como "verdadeiro" quebra
em múltiplos tokens no vocabulário do modelo ("verdade" + "iro"), então
checar "qual é o logprob do token da palavra X" simplesmente não encontra a
opção. Uma letra maiúscula isolada é, na prática, sempre um único token,
em qualquer idioma -- validado manualmente antes de integrar aqui.

Mitiga viés de posição (modelos pequenos tendem a favorecer a opção A)
rodando a classificação duas vezes com a ordem das opções invertida e
tirando a média das probabilidades por opção.

Duas implementações, mesma interface async `classify(question, options)`:
- JevClassifier: carrega o modelo (~alguns GB) no próprio processo.
- RemoteJevClassifier: chama o serviço `jev` (app/jev_server.py) por HTTP.

Por que um serviço separado: cada processo que instanciasse JevClassifier
carregava sua PRÓPRIA cópia do modelo -- medido ao vivo (28/09/2026), rodar
api + worker + um script de calibração ao mesmo tempo (3 cópias) estourou a
RAM do Docker Desktop (16GB) e derrubou os três por OOM. Com um serviço
único, existe só uma cópia do modelo na memória não importa quantos
processos usem o classificador; get_jev_classifier() devolve o cliente
remoto sempre que JEV_SERVER_URL está configurado.
"""

import logging
import math
from asyncio import Lock, to_thread
from string import ascii_uppercase
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger("contraria.jev")

_MAX_OPTIONS = len(ascii_uppercase)


class JevClassifierPort(Protocol):
    async def classify(self, question: str, options: list[str]) -> dict[str, float]: ...


def _validate_options(options: list[str]) -> None:
    if not 2 <= len(options) <= _MAX_OPTIONS:
        raise ValueError(f"classify aceita entre 2 e {_MAX_OPTIONS} opções")
    if len(options) != len(set(options)):
        raise ValueError("as opções não podem se repetir")


class JevClassifier:
    """Classificador local de poucas opções via logprobs, no próprio processo.

    Usado pelo serviço `jev` (única cópia do modelo) e, sem JEV_SERVER_URL
    configurado, também diretamente por quem chamar get_jev_classifier --
    útil para testes/scripts avulsos, mas evite em produção (ver módulo).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._llm = None
        self._load_lock = Lock()
        self._infer_lock = Lock()  # uma instância do llama.cpp não é thread-safe

    async def _ensure_loaded(self):
        if self._llm is not None:
            return self._llm
        async with self._load_lock:
            if self._llm is not None:
                return self._llm

            def _load():
                from huggingface_hub import hf_hub_download
                from llama_cpp import Llama

                logger.info(
                    "carregando modelo Jev (%s/%s)",
                    self.settings.jev_model_repo,
                    self.settings.jev_model_file,
                )
                model_path = hf_hub_download(
                    repo_id=self.settings.jev_model_repo,
                    filename=self.settings.jev_model_file,
                )
                llm = Llama(
                    model_path=model_path,
                    n_ctx=self.settings.jev_n_ctx,
                    n_threads=self.settings.jev_n_threads or None,
                    n_gpu_layers=0,
                    verbose=False,
                    logits_all=True,
                )
                logger.info("modelo Jev carregado de %s", model_path)
                return llm

            self._llm = await to_thread(_load)
        return self._llm

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        """Classifica `question` entre `options`; devolve prob. por opção (soma 1)."""
        _validate_options(options)
        async with self._infer_lock:
            forward = await self._classify_ordered(question, options)
            backward = await self._classify_ordered(question, list(reversed(options)))
        return {opt: (forward[opt] + backward[opt]) / 2 for opt in options}

    async def _classify_ordered(self, question: str, options: list[str]) -> dict[str, float]:
        llm = await self._ensure_loaded()
        letters = ascii_uppercase[: len(options)]
        menu = "\n".join(f"{letter}) {opt}" for letter, opt in zip(letters, options, strict=True))
        prompt = f"{question}\n{menu}\nResponda só com a letra.\nResposta:"

        def _infer():
            return llm(
                prompt, max_tokens=1, logprobs=len(options) + 10, echo=False, temperature=0.0
            )

        result = await to_thread(_infer)
        top_logprobs = result["choices"][0]["logprobs"]["top_logprobs"][0]

        letter_logprobs = {
            letter: max(top_logprobs.get(letter, -1e9), top_logprobs.get(" " + letter, -1e9))
            for letter in letters
        }
        max_lp = max(letter_logprobs.values())
        exp = {k: math.exp(v - max_lp) for k, v in letter_logprobs.items()}
        total = sum(exp.values())
        probs_by_letter = {k: v / total for k, v in exp.items()}
        return {opt: probs_by_letter[letter] for letter, opt in zip(letters, options, strict=True)}


class RemoteJevClassifier:
    """Cliente HTTP pro serviço `jev` -- uma cópia do modelo, todo mundo usa."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        _validate_options(options)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/classify",
                json={"question": question, "options": options},
            )
            response.raise_for_status()
        return response.json()["probabilities"]


_default_classifier: JevClassifierPort | None = None


def get_jev_classifier(settings: Settings | None = None) -> JevClassifierPort:
    """Singleton do processo.

    Com JEV_SERVER_URL configurado (o normal em produção, via docker-compose),
    devolve um cliente HTTP pro serviço `jev` -- sem isso, carrega o modelo
    (~alguns GB) no próprio processo, o que é aceitável isoladamente (um
    script avulso, um teste manual) mas nunca com vários processos ao mesmo
    tempo, sob risco de repetir o OOM medido ao vivo.
    """
    global _default_classifier
    if _default_classifier is None:
        resolved = settings or get_settings()
        if resolved.jev_server_url:
            _default_classifier = RemoteJevClassifier(resolved.jev_server_url)
        else:
            _default_classifier = JevClassifier(resolved)
    return _default_classifier

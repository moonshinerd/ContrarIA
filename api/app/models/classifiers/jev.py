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
"""

import logging
import math
from string import ascii_uppercase
from threading import Lock

from app.core.config import Settings, get_settings

logger = logging.getLogger("contraria.jev")

_MAX_OPTIONS = len(ascii_uppercase)


class JevClassifier:
    """Classificador local de poucas opções via logprobs (mecanismo "Jev")."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._llm = None
        self._load_lock = Lock()

    def _ensure_loaded(self):
        if self._llm is not None:
            return self._llm
        with self._load_lock:
            if self._llm is not None:
                return self._llm
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
            self._llm = Llama(
                model_path=model_path,
                n_ctx=self.settings.jev_n_ctx,
                n_threads=self.settings.jev_n_threads or None,
                n_gpu_layers=0,
                verbose=False,
                logits_all=True,
            )
            logger.info("modelo Jev carregado de %s", model_path)
        return self._llm

    def classify(self, question: str, options: list[str]) -> dict[str, float]:
        """Classifica `question` entre `options`; devolve prob. por opção (soma 1)."""
        if not 2 <= len(options) <= _MAX_OPTIONS:
            raise ValueError(f"classify aceita entre 2 e {_MAX_OPTIONS} opções")
        if len(options) != len(set(options)):
            raise ValueError("as opções não podem se repetir")

        forward = self._classify_ordered(question, options)
        reversed_options = list(reversed(options))
        backward = self._classify_ordered(question, reversed_options)

        return {opt: (forward[opt] + backward[opt]) / 2 for opt in options}

    def _classify_ordered(self, question: str, options: list[str]) -> dict[str, float]:
        llm = self._ensure_loaded()
        letters = ascii_uppercase[: len(options)]
        menu = "\n".join(f"{letter}) {opt}" for letter, opt in zip(letters, options, strict=True))
        prompt = f"{question}\n{menu}\nResponda só com a letra.\nResposta:"

        result = llm(
            prompt,
            max_tokens=1,
            logprobs=len(options) + 10,
            echo=False,
            temperature=0.0,
        )
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


_default_classifier: JevClassifier | None = None


def get_jev_classifier(settings: Settings | None = None) -> JevClassifier:
    """Singleton do processo -- carregar o modelo (~alguns GB em RAM) uma vez só."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = JevClassifier(settings)
    return _default_classifier

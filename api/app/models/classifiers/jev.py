"""Classificador local Jev via NLI (Natural Language Inference) usando
MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7.

Substitui o antigo Qwen3-4B-GGUF autorregressivo:
1. Modelo discriminativo Cross-Encoder especializado em inferência de premissa e hipótese.
2. Classe 'neutral' nativa, eliminando falsos positivos onde a ausência de confirmação
   era tratada como desmentido.
3. Pegada de memória de apenas ~500MB (contra ~3.5GB) e latência em CPU de ~50-80ms por par.
4. Sem necessidade de compilação C++ de llama-cpp-python nem travas frágeis de regex.

Duas implementações, mesma interface async:
- JevClassifier: carrega o modelo (~500MB) no próprio processo.
- RemoteJevClassifier: chama o serviço `jev` (app/jev_server.py) por HTTP.
"""

import logging
import re
from asyncio import Lock, to_thread
from string import ascii_uppercase
from typing import Protocol

import httpx
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import Settings, get_settings

logger = logging.getLogger("contraria.jev")

_MAX_OPTIONS = len(ascii_uppercase)
PROMPT_OVERHEAD_TOKENS = 32


class JevClassifierPort(Protocol):
    async def classify(self, question: str, options: list[str]) -> dict[str, float]: ...

    async def count_tokens(self, texts: list[str]) -> list[int]: ...

    async def predict_nli(self, premise: str, hypothesis: str) -> dict[str, float]: ...

    async def predict_nli_batch(self, pairs: list[tuple[str, str]]) -> list[dict[str, float]]: ...


def _validate_options(options: list[str]) -> None:
    if not 2 <= len(options) <= _MAX_OPTIONS:
        raise ValueError(f"classify aceita entre 2 e {_MAX_OPTIONS} opções")
    if len(options) != len(set(options)):
        raise ValueError("as opções não podem se repetir")


class JevClassifier:
    """Classificador local NLI / Zero-Shot baseado em mDeBERTa-v3."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tokenizer: AutoTokenizer | None = None
        self._model: AutoModelForSequenceClassification | None = None
        self._load_lock = Lock()
        self._infer_lock = Lock()

    async def _ensure_loaded(self) -> tuple[AutoTokenizer, AutoModelForSequenceClassification]:
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

        async with self._load_lock:
            if self._tokenizer is not None and self._model is not None:
                return self._tokenizer, self._model

            def _load():
                logger.info("carregando modelo Jev NLI (%s)", self.settings.jev_model_repo)
                if self.settings.jev_n_threads and self.settings.jev_n_threads > 0:
                    torch.set_num_threads(self.settings.jev_n_threads)

                tok = AutoTokenizer.from_pretrained(self.settings.jev_model_repo)
                mod = AutoModelForSequenceClassification.from_pretrained(
                    self.settings.jev_model_repo
                )
                mod.eval()
                logger.info(
                    "modelo Jev NLI carregado com sucesso (%s)", self.settings.jev_model_repo
                )
                return tok, mod

            self._tokenizer, self._model = await to_thread(_load)
        return self._tokenizer, self._model

    async def count_tokens(self, texts: list[str]) -> list[int]:
        """Contagem real de tokens no vocabulário do mDeBERTa."""
        tokenizer, _ = await self._ensure_loaded()

        def _count():
            return [len(tokenizer.encode(t, add_special_tokens=False)) for t in texts]

        return await to_thread(_count)

    async def predict_nli(self, premise: str, hypothesis: str) -> dict[str, float]:
        """Calcula probabilidades NLI para um único par (premise, hypothesis)."""
        results = await self.predict_nli_batch([(premise, hypothesis)])
        return results[0]

    async def predict_nli_batch(self, pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
        """Calcula probabilidades NLI em lote na CPU."""
        if not pairs:
            return []

        tokenizer, model = await self._ensure_loaded()

        def _infer():
            premises = [p[0][:1500] for p in pairs]
            hypotheses = [p[1][:500] for p in pairs]
            inputs = tokenizer(
                premises,
                hypotheses,
                truncation="longest_first",
                max_length=512,
                padding=True,
                return_tensors="pt",
            )
            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1).tolist()

            id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
            results = []
            for row in probs:
                results.append({id2label[i]: float(row[i]) for i in range(len(row))})
            return results

        async with self._infer_lock:
            return await to_thread(_infer)

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        """Interface universal de classificação compatível com Jev.

        Mapeia os cenários do ContrarIA diretamente para inferência lógica de NLI:
        - Factual vs Opinião
        - Relevância de evidência
        - Veredito contra premissa/alegação
        - Classificação Zero-Shot genérica
        """
        _validate_options(options)
        opt_set = set(options)

        # 1. Triagem de alegações: Factual vs Opinião
        if {"factual", "opiniao"} <= opt_set:
            match = re.search(r'Frase:\s*"([^"]+)"', question)
            sentence = match.group(1) if match else question
            nli_results = await self.predict_nli_batch(
                [
                    (sentence, "Este texto descreve um fato objetivo."),
                    (sentence, "Este texto é uma opinião pessoal ou desabafo."),
                ]
            )
            score_f = nli_results[0]["entailment"]
            score_o = nli_results[1]["entailment"]
            probs = torch.softmax(torch.tensor([score_f, score_o]), dim=0).tolist()
            mapping = {"factual": probs[0], "opiniao": probs[1]}
            return {opt: mapping[opt] for opt in options}

        # 2. Filtragem de relevância: Relevante vs Irrelevante
        if {"relevante", "irrelevante"} <= opt_set:
            claim_match = re.search(r'Alegação(?: a verificar)?:\s*"([^"]+)"', question)
            snippet_match = re.search(r'Trecho(?: de fonte)?:\s*"([^"]+)"', question)
            if claim_match and snippet_match:
                premise = snippet_match.group(1)
                hypothesis = claim_match.group(1)
                nli_res = await self.predict_nli(premise, hypothesis)
                rel = nli_res["entailment"] + nli_res["contradiction"]
                irrel = nli_res["neutral"]
                mapping = {"relevante": rel, "irrelevante": irrel}
                return {opt: mapping[opt] for opt in options}

        # 3. Veredito de fato: Confirmam vs Desmentem vs Enganoso/Outros
        if any("desmentem" in opt for opt in options):
            claim_match = re.search(r'Alegação:\s*"([^"]+)"', question)
            claim = claim_match.group(1) if claim_match else question
            evidence = question
            if "Evidências encontradas:\n" in question:
                ev_part = question.split("Evidências encontradas:\n", 1)[1]
                if "O que as evidências acima dizem" in ev_part:
                    evidence = ev_part.split("O que as evidências acima dizem", 1)[0].strip()

            nli_res = await self.predict_nli(evidence, claim)
            e = nli_res["entailment"]
            c = nli_res["contradiction"]
            n = nli_res["neutral"]

            res: dict[str, float] = {}
            for opt in options:
                if "confirmam a alegação" in opt:
                    res[opt] = e
                elif "desmentem a alegação" in opt:
                    res[opt] = c
                elif any(
                    term in opt
                    for term in ("insuficiente", "não contêm", "não tratam", "inconclusiv")
                ):
                    res[opt] = n
                else:
                    # Distorcem / Exagero / Misleading
                    res[opt] = min(e, c) * 2.0 if (e > 0.15 and c > 0.15) else 0.05

            tot = sum(res.values()) or 1.0
            return {k: v / tot for k, v in res.items()}

        # 4. Fallback genérico: Zero-Shot por NLI
        hypotheses = [(question[:400], f"A resposta correta é: {opt}.") for opt in options]
        batch_nli = await self.predict_nli_batch(hypotheses)
        scores = [item["entailment"] for item in batch_nli]
        probs = torch.softmax(torch.tensor(scores), dim=0).tolist()
        return dict(zip(options, probs, strict=True))


class RemoteJevClassifier:
    """Cliente HTTP para o serviço `jev` -- uma cópia do modelo compartilhada."""

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

    async def count_tokens(self, texts: list[str]) -> list[int]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/count_tokens", json={"texts": texts})
            response.raise_for_status()
        return response.json()["counts"]

    async def predict_nli(self, premise: str, hypothesis: str) -> dict[str, float]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/nli",
                json={"premise": premise, "hypothesis": hypothesis},
            )
            response.raise_for_status()
        return response.json()["probabilities"]

    async def predict_nli_batch(self, pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
        payload = [{"premise": p[0], "hypothesis": p[1]} for p in pairs]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/nli_batch",
                json={"pairs": payload},
            )
            response.raise_for_status()
        return response.json()["results"]


_default_classifier: JevClassifierPort | None = None


def get_jev_classifier(settings: Settings | None = None) -> JevClassifierPort:
    """Singleton do processo para o classificador Jev."""
    global _default_classifier
    if _default_classifier is None:
        resolved = settings or get_settings()
        if resolved.jev_server_url:
            _default_classifier = RemoteJevClassifier(resolved.jev_server_url)
        else:
            _default_classifier = JevClassifier(resolved)
    return _default_classifier

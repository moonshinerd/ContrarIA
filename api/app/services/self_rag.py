"""Self-RAG factored para responder às perguntas CoVe com evidências externas."""

import asyncio
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.clients.evidence import get_evidence_source
from app.clients.evidence.base import EvidenceSource
from app.clients.evidence.google_factcheck import GoogleFactCheckClient
from app.core.config import Settings, get_settings
from app.domain.entities import Evidence, Verdict
from app.models.llm.base import LLMPort
from app.services.claim_verification import CoVeQuestionPlan
from app.services.prompts_loader import load_prompt


class SupportLevel(StrEnum):
    FULLY = "fully"
    PARTIALLY = "partially"
    NO_SUPPORT = "no_support"


class RetrievalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    retrieve: bool
    rationale: str = Field(min_length=3, max_length=600)


class EvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(pattern=r"^q\d{2,3}:[a-z0-9_-]+:\d{2}$")
    source: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2000)
    title: str = Field(max_length=1000)
    snippet: str = Field(max_length=5000)
    published_at: datetime | None = None
    rating: str | None = Field(default=None, max_length=500)

    @classmethod
    def from_domain(cls, evidence: Evidence, evidence_id: str) -> "EvidenceDocument":
        return cls(
            evidence_id=evidence_id,
            source=evidence.source,
            url=evidence.url[:2000],
            title=evidence.title[:1000],
            snippet=evidence.snippet[:5000],
            published_at=evidence.published_at,
            rating=evidence.rating[:500] if evidence.rating else None,
        )


class RelevanceJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str
    relevant: bool
    rationale: str = Field(min_length=3, max_length=600)


class RelevanceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RelevanceJudgment] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def reject_duplicate_evidence(self) -> "RelevanceAssessment":
        identifiers = [item.evidence_id for item in self.items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("A avaliação contém evidências duplicadas")
        return self


class AnswerAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str | None = Field(default=None, max_length=4000)
    support: SupportLevel
    usefulness: int = Field(ge=1, le=5)
    evidence_ids: list[str] = Field(max_length=200)
    rationale: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def enforce_supported_answer(self) -> "AnswerAssessment":
        if self.support is SupportLevel.NO_SUPPORT:
            if self.answer is not None or self.evidence_ids:
                raise ValueError("Resposta sem suporte não pode conter resposta ou citações")
        elif not self.answer or not self.evidence_ids:
            raise ValueError("Resposta sustentada exige texto e ao menos uma citação")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("A resposta contém citações duplicadas")
        return self


class QuestionReflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    question: str
    purpose: str
    retrieval: RetrievalDecision
    retrieved_evidence: list[EvidenceDocument]
    relevance: list[RelevanceJudgment]
    answer: AnswerAssessment
    source_errors: dict[str, str] = Field(default_factory=dict)

    @property
    def relevant_evidence(self) -> list[EvidenceDocument]:
        relevant_ids = {item.evidence_id for item in self.relevance if item.relevant}
        return [item for item in self.retrieved_evidence if item.evidence_id in relevant_ids]


class SupportedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    question: str
    answer: str
    support: SupportLevel
    usefulness: int
    evidence: list[EvidenceDocument]


class SelfRAGResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reflections: list[QuestionReflection]
    supported_answers: list[SupportedAnswer]
    agent_outputs: dict[str, str]
    llm_calls: int = Field(ge=0)
    truncated_questions: int = Field(ge=0)

    def persist_in_verdict(self, verdict: Verdict) -> None:
        """Copia a auditoria estruturada para o contrato consumido pelas issues #24/#25."""
        verdict.agent_outputs.update(self.agent_outputs)


class SelfRAGLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_questions: int = Field(default=10, ge=1, le=100)
    max_evidence_per_source: int = Field(default=3, ge=1, le=20)
    max_llm_calls: int = Field(default=30, ge=1, le=300)
    evidence_timeout_seconds: float = Field(default=20, gt=0, le=120)

    @classmethod
    def from_settings(cls, settings: Settings) -> "SelfRAGLimits":
        return cls(
            max_questions=settings.self_rag_max_questions,
            max_evidence_per_source=settings.self_rag_max_evidence_per_source,
            max_llm_calls=settings.self_rag_max_llm_calls,
            evidence_timeout_seconds=settings.evidence_timeout_seconds,
        )


class StructuredSelfRAGOutputError(ValueError):
    """O LLM não produziu uma reflexão válida após a tentativa de correção."""


class SelfRAGCallLimitExceeded(RuntimeError):
    """O limite de chamadas do Self-RAG foi atingido antes de concluir o plano."""


class _CallBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.maximum:
            raise SelfRAGCallLimitExceeded(
                f"Limite de {self.maximum} chamadas de LLM atingido no Self-RAG"
            )
        self.used += 1


ValidatedModel = TypeVar("ValidatedModel", bound=BaseModel)


class SelfRAGService:
    """Recupera, filtra e responde cada pergunta CoVe de forma isolada."""

    def __init__(
        self,
        llm: LLMPort,
        sources: list[EvidenceSource],
        *,
        limits: SelfRAGLimits | None = None,
    ) -> None:
        names = [source.name for source in sources]
        if len(names) != len(set(names)):
            raise ValueError("As fontes habilitadas não podem ter nomes duplicados")
        safe_names = [self._safe_source_name(name) for name in names]
        if len(safe_names) != len(set(safe_names)):
            raise ValueError("Os nomes normalizados das fontes não podem ser duplicados")
        self.llm = llm
        self.sources = list(sources)
        self.limits = limits or SelfRAGLimits()

    @classmethod
    def from_settings(
        cls,
        llm: LLMPort,
        settings: Settings | None = None,
    ) -> "SelfRAGService":
        resolved = settings or get_settings()
        sources: list[EvidenceSource] = []
        for name in resolved.self_rag_enabled_sources:
            if name == GoogleFactCheckClient.name:
                source = GoogleFactCheckClient(api_key=resolved.google_factcheck_api_key)
            else:
                source = get_evidence_source(name, settings=resolved)
            sources.append(source)
        return cls(llm, sources, limits=SelfRAGLimits.from_settings(resolved))

    async def run(
        self,
        plan: CoVeQuestionPlan,
        *,
        current_date: date | None = None,
    ) -> SelfRAGResult:
        analysis_date = current_date or datetime.now(UTC).date()
        questions = [
            (claim.claim, question.question, question.purpose)
            for claim in plan.claims
            for question in claim.questions
        ]
        selected = questions[: self.limits.max_questions]
        budget = _CallBudget(self.limits.max_llm_calls)
        outputs: dict[str, str] = {}
        reflections: list[QuestionReflection] = []
        supported_answers: list[SupportedAnswer] = []

        for index, (claim, question, purpose) in enumerate(selected, start=1):
            reflection = await self._answer_question(
                index=index,
                claim=claim,
                question=question,
                purpose=purpose,
                current_date=analysis_date,
                budget=budget,
                outputs=outputs,
            )
            reflections.append(reflection)
            if reflection.answer.support is not SupportLevel.NO_SUPPORT:
                cited = set(reflection.answer.evidence_ids)
                supported_answers.append(
                    SupportedAnswer(
                        claim=claim,
                        question=question,
                        answer=reflection.answer.answer or "",
                        support=reflection.answer.support,
                        usefulness=reflection.answer.usefulness,
                        evidence=[
                            item
                            for item in reflection.relevant_evidence
                            if item.evidence_id in cited
                        ],
                    )
                )

        truncated = len(questions) - len(selected)
        outputs["self_rag.limits"] = json.dumps(
            {
                "processed_questions": len(selected),
                "truncated_questions": truncated,
                "llm_calls": budget.used,
                "max_llm_calls": budget.maximum,
            },
            ensure_ascii=False,
        )
        return SelfRAGResult(
            reflections=reflections,
            supported_answers=supported_answers,
            agent_outputs=outputs,
            llm_calls=budget.used,
            truncated_questions=truncated,
        )

    async def _answer_question(
        self,
        *,
        index: int,
        claim: str,
        question: str,
        purpose: str,
        current_date: date,
        budget: _CallBudget,
        outputs: dict[str, str],
    ) -> QuestionReflection:
        prefix = f"self_rag.q{index:02d}"
        retrieval = await self._complete_validated(
            prompt="self_rag_retrieve",
            payload={"claim": claim, "question": question, "purpose": purpose},
            response_type=RetrievalDecision,
            purpose="self_rag_retrieve",
            current_date=current_date,
            budget=budget,
            post_validate=lambda result: None,
        )
        outputs[f"{prefix}.[Retrieve]"] = retrieval.model_dump_json()

        if not retrieval.retrieve:
            return self._unsupported_reflection(
                prefix, claim, question, purpose, retrieval, [], [], {}, outputs
            )

        evidences, source_errors = await self._retrieve(question, index=index)
        outputs[f"{prefix}.[Sources]"] = json.dumps(
            {
                "evidence": [item.model_dump(mode="json") for item in evidences],
                "source_errors": source_errors,
            },
            ensure_ascii=False,
        )
        if not evidences:
            return self._unsupported_reflection(
                prefix,
                claim,
                question,
                purpose,
                retrieval,
                evidences,
                [],
                source_errors,
                outputs,
            )

        evidence_ids = [item.evidence_id for item in evidences]
        relevance = await self._complete_validated(
            prompt="self_rag_relevance",
            payload={
                "question": question,
                "evidence": [item.model_dump(mode="json") for item in evidences],
            },
            response_type=RelevanceAssessment,
            purpose="self_rag_isrel",
            current_date=current_date,
            budget=budget,
            post_validate=lambda result: self._require_evidence_coverage(
                result.items, evidence_ids
            ),
        )
        outputs[f"{prefix}.[IsRel]"] = relevance.model_dump_json()
        relevant_ids = {item.evidence_id for item in relevance.items if item.relevant}
        relevant = [item for item in evidences if item.evidence_id in relevant_ids]
        if not relevant:
            return self._unsupported_reflection(
                prefix,
                claim,
                question,
                purpose,
                retrieval,
                evidences,
                relevance.items,
                source_errors,
                outputs,
            )

        answer = await self._complete_validated(
            prompt="self_rag_answer",
            payload={
                "claim": claim,
                "question": question,
                "evidence": [item.model_dump(mode="json") for item in relevant],
            },
            response_type=AnswerAssessment,
            purpose="self_rag_answer",
            current_date=current_date,
            budget=budget,
            post_validate=lambda result: self._validate_answer(result, relevant_ids, relevant),
        )
        outputs[f"{prefix}.[IsSup][IsUse]"] = answer.model_dump_json()
        return QuestionReflection(
            claim=claim,
            question=question,
            purpose=purpose,
            retrieval=retrieval,
            retrieved_evidence=evidences,
            relevance=relevance.items,
            answer=answer,
            source_errors=source_errors,
        )

    async def _retrieve(
        self, question: str, *, index: int
    ) -> tuple[list[EvidenceDocument], dict[str, str]]:
        async def search(source: EvidenceSource):
            try:
                found = await asyncio.wait_for(
                    source.search(question, limit=self.limits.max_evidence_per_source),
                    timeout=self.limits.evidence_timeout_seconds,
                )
                return source.name, found[: self.limits.max_evidence_per_source], None
            except Exception as exc:
                return source.name, [], type(exc).__name__

        results = await asyncio.gather(*(search(source) for source in self.sources))
        documents: list[EvidenceDocument] = []
        errors: dict[str, str] = {}
        for source_name, found, error in results:
            if error:
                errors[source_name] = error
                continue
            safe_source = self._safe_source_name(source_name)
            for evidence_index, evidence in enumerate(found, start=1):
                evidence_id = f"q{index:02d}:{safe_source or 'fonte'}:{evidence_index:02d}"
                documents.append(EvidenceDocument.from_domain(evidence, evidence_id))
        return documents, errors

    @staticmethod
    def _safe_source_name(source_name: str) -> str:
        normalized = unicodedata.normalize("NFKD", source_name.casefold())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        return re.sub(r"[^a-z0-9_-]+", "_", normalized).strip("_") or "fonte"

    def _unsupported_reflection(
        self,
        prefix: str,
        claim: str,
        question: str,
        purpose: str,
        retrieval: RetrievalDecision,
        evidences: list[EvidenceDocument],
        relevance: list[RelevanceJudgment],
        source_errors: dict[str, str],
        outputs: dict[str, str],
    ) -> QuestionReflection:
        answer = AnswerAssessment(
            answer=None,
            support=SupportLevel.NO_SUPPORT,
            usefulness=1,
            evidence_ids=[],
            rationale="Nenhuma evidência relevante sustenta uma resposta.",
        )
        outputs.setdefault(f"{prefix}.[IsRel]", json.dumps({"items": []}, ensure_ascii=False))
        outputs[f"{prefix}.[IsSup][IsUse]"] = answer.model_dump_json()
        return QuestionReflection(
            claim=claim,
            question=question,
            purpose=purpose,
            retrieval=retrieval,
            retrieved_evidence=evidences,
            relevance=relevance,
            answer=answer,
            source_errors=source_errors,
        )

    async def _complete_validated(
        self,
        *,
        prompt: str,
        payload: dict,
        response_type: type[ValidatedModel],
        purpose: str,
        current_date: date,
        budget: _CallBudget,
        post_validate,
    ) -> ValidatedModel:
        system = load_prompt(prompt).replace("{{CURRENT_DATE}}", current_date.isoformat())
        validation_error: Exception | None = None
        for attempt in range(3):
            retry = ""
            if attempt:
                retry = (
                    "\n\nA resposta anterior falhou na validação. Gere novamente somente o JSON "
                    "e obedeça exatamente ao esquema e aos identificadores recebidos."
                )
            budget.consume()
            raw = await self.llm.complete(
                system=system + retry,
                user=json.dumps(payload, ensure_ascii=False),
                json_mode=True,
                purpose=purpose,
            )
            try:
                result = response_type.model_validate_json(raw)
                post_validate(result)
                return result
            except (ValidationError, ValueError) as exc:
                validation_error = exc
        raise StructuredSelfRAGOutputError(
            f"Resposta inválida para {purpose} após 3 tentativas"
        ) from validation_error

    @staticmethod
    def _require_evidence_coverage(
        received: list[RelevanceJudgment], expected_ids: list[str]
    ) -> None:
        if [item.evidence_id for item in received] != expected_ids:
            raise ValueError("[IsRel] deve cobrir todas as evidências uma vez e na ordem recebida")

    @staticmethod
    def _validate_answer(
        answer: AnswerAssessment,
        relevant_ids: set[str],
        relevant: list[EvidenceDocument],
    ) -> None:
        if not set(answer.evidence_ids).issubset(relevant_ids):
            raise ValueError("A resposta citou evidência ausente ou classificada como irrelevante")
        if answer.support is SupportLevel.NO_SUPPORT:
            return
        evidence_text = " ".join(
            part for item in relevant for part in (item.title, item.snippet, item.rating or "")
        )
        answer_words = SelfRAGService._significant_words(answer.answer or "")
        evidence_words = SelfRAGService._significant_words(evidence_text)
        coverage = len(answer_words & evidence_words) / max(len(answer_words), 1)
        if coverage < 0.35:
            raise ValueError("A resposta não está textualmente ancorada nas evidências citadas")

    @staticmethod
    def _significant_words(text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text.casefold().replace("_", " "))
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        stopwords = {
            "a",
            "ao",
            "as",
            "com",
            "da",
            "das",
            "de",
            "do",
            "dos",
            "e",
            "em",
            "na",
            "nas",
            "no",
            "nos",
            "o",
            "os",
            "para",
            "por",
            "que",
            "um",
            "uma",
        }
        return {
            word
            for word in re.findall(r"\w+", normalized)
            if len(word) >= 3 and word not in stopwords
        }

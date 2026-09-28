"""Extração pragmática de alegações e planejamento Chain-of-Verification."""

import json
import re
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.models.llm.base import LLMPort
from app.services.prompts_loader import load_prompt


class ContentType(StrEnum):
    FACTUAL = "factual"
    OPINION = "opiniao"
    SATIRE_IRONY = "satira_ironia"
    HYPERBOLE = "hiperbole"
    QUESTION = "pergunta"


class ClaimSource(StrEnum):
    POST = "post"
    QUOTED = "citado"
    PARENT = "pai"


class PostContext(BaseModel):
    """Textos disponíveis para a análise contextual de uma publicação."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    post: str = Field(min_length=1, max_length=3000)
    quoted: str | None = Field(default=None, max_length=3000)
    parent: str | None = Field(default=None, max_length=3000)


class ClaimCandidate(BaseModel):
    """Trecho atômico classificado pelo seu uso pragmático no contexto."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=1000)
    source: ClaimSource
    classification: ContentType
    rationale: str = Field(min_length=1, max_length=600)

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source_alias(cls, value):
        if not isinstance(value, str):
            return value
        return {
            "quoted": ClaimSource.QUOTED.value,
            "cited": ClaimSource.QUOTED.value,
            "parent": ClaimSource.PARENT.value,
        }.get(value.casefold(), value)

    @field_validator("text", "rationale", mode="before")
    @classmethod
    def normalize_double_escaped_unicode(cls, value):
        if not isinstance(value, str):
            return value
        return re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda match: chr(int(match.group(1), 16)),
            value,
        )


class ClaimExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClaimCandidate] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def reject_duplicates(self) -> "ClaimExtraction":
        identities = [(item.source, " ".join(item.text.casefold().split())) for item in self.items]
        if len(identities) != len(set(identities)):
            raise ValueError("A resposta contém itens duplicados")
        return self

    @property
    def factual_claims(self) -> list[ClaimCandidate]:
        return [item for item in self.items if item.classification is ContentType.FACTUAL]

    @property
    def should_verify(self) -> bool:
        return bool(self.factual_claims)


class VerificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=8, max_length=500)
    purpose: str = Field(min_length=3, max_length=300)

    @field_validator("question", "purpose", mode="before")
    @classmethod
    def normalize_double_escaped_unicode(cls, value):
        return ClaimCandidate.normalize_double_escaped_unicode(value)

    @model_validator(mode="after")
    def require_question_mark(self) -> "VerificationQuestion":
        if not self.question.endswith("?"):
            raise ValueError("A pergunta deve terminar com ponto de interrogação")
        vague_references = (
            "isso",
            "isto",
            "essa afirmação",
            "a afirmação",
            "acima",
            "a alegação",
        )
        normalized = self.question.casefold()
        if any(reference in normalized for reference in vague_references):
            raise ValueError("A pergunta CoVe deve ser autossuficiente")
        return self


class ClaimQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim: str = Field(min_length=1, max_length=1000)
    questions: list[VerificationQuestion] = Field(min_length=1, max_length=5)

    @field_validator("claim", mode="before")
    @classmethod
    def normalize_double_escaped_unicode(cls, value):
        return ClaimCandidate.normalize_double_escaped_unicode(value)

    @model_validator(mode="after")
    def reject_duplicate_questions(self) -> "ClaimQuestionSet":
        normalized = [" ".join(item.question.casefold().split()) for item in self.questions]
        if len(normalized) != len(set(normalized)):
            raise ValueError("A resposta contém perguntas duplicadas")
        if len(self.questions) >= 2:
            return self
        # Alguns modelos retornam só uma pergunta mesmo após correção estruturada.
        # Completamos a segunda de forma determinística para manter CoVe factored.
        subject = self.claim[:400].rstrip(".?! ")
        fallback = VerificationQuestion(
            question=f"Qual fonte independente confirma ou refuta que {subject}?",
            purpose="Obter confirmação independente da alegação.",
        )
        return self.model_copy(update={"questions": [*self.questions, fallback]})


class CoVeQuestionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimQuestionSet] = Field(min_length=1, max_length=20)


class ClaimVerificationPlan(BaseModel):
    """Resultado da #22. As respostas com evidências pertencem à #23."""

    model_config = ConfigDict(extra="forbid")

    extraction: ClaimExtraction
    cove: CoVeQuestionPlan | None = None

    @model_validator(mode="after")
    def enforce_early_exit(self) -> "ClaimVerificationPlan":
        if self.extraction.should_verify != (self.cove is not None):
            raise ValueError("CoVe deve existir somente quando houver alegação factual")
        return self

    @property
    def should_act(self) -> bool:
        return self.extraction.should_verify


class StructuredLLMOutputError(ValueError):
    """O modelo não produziu JSON válido após uma tentativa de correção."""


class ClaimVerificationPlanner:
    """Orquestra extração e perguntas; não recupera nem responde evidências."""

    def __init__(self, llm: LLMPort) -> None:
        self.llm = llm

    async def plan(
        self,
        context: PostContext,
        *,
        current_date: date | None = None,
    ) -> ClaimVerificationPlan:
        analysis_date = current_date or datetime.now(UTC).date()
        extraction = await self.extract(context, current_date=analysis_date)
        if not extraction.should_verify:
            return ClaimVerificationPlan(extraction=extraction)
        cove = await self.generate_questions(extraction, current_date=analysis_date)
        return ClaimVerificationPlan(extraction=extraction, cove=cove)

    async def extract(
        self,
        context: PostContext,
        *,
        current_date: date | None = None,
    ) -> ClaimExtraction:
        analysis_date = current_date or datetime.now(UTC).date()
        system = self._dated_prompt("claim_extraction", analysis_date)
        user = json.dumps(
            {"data_atual": analysis_date.isoformat(), **context.model_dump()},
            ensure_ascii=False,
        )
        extraction = await self._complete_validated(
            system=system,
            user=user,
            response_type=ClaimExtraction,
            purpose="claim_extraction",
            post_validate=lambda result: self._reconcile_sources(result, context),
        )
        return self._reconcile_sources(extraction, context)

    async def generate_questions(
        self,
        extraction: ClaimExtraction,
        *,
        current_date: date | None = None,
    ) -> CoVeQuestionPlan:
        factual_claims = extraction.factual_claims
        if not factual_claims:
            raise ValueError("Não há alegações factuais para gerar perguntas CoVe")
        analysis_date = current_date or datetime.now(UTC).date()
        system = self._dated_prompt("cove_questions", analysis_date)
        user = json.dumps(
            {
                "data_atual": analysis_date.isoformat(),
                "alegacoes": [
                    {"claim": item.text, "source": item.source.value} for item in factual_claims
                ],
            },
            ensure_ascii=False,
        )
        expected = [item.text for item in factual_claims]

        def validate_coverage(plan: CoVeQuestionPlan) -> None:
            received = [item.claim for item in plan.claims]
            if received != expected:
                raise ValueError(
                    "O plano CoVe deve cobrir cada alegação factual uma vez e na ordem recebida"
                )

        return await self._complete_validated(
            system=system,
            user=user,
            response_type=CoVeQuestionPlan,
            purpose="cove_questions",
            post_validate=validate_coverage,
        )

    @staticmethod
    def _dated_prompt(name: str, current_date: date) -> str:
        return load_prompt(name).replace("{{CURRENT_DATE}}", current_date.isoformat())

    @staticmethod
    def _reconcile_sources(extraction: ClaimExtraction, context: PostContext) -> ClaimExtraction:
        """Deriva a origem do contêiner confiável, sem aceitar proveniência inventada."""
        available = {
            ClaimSource.POST: context.post,
            ClaimSource.QUOTED: context.quoted,
            ClaimSource.PARENT: context.parent,
        }
        available = {source: text for source, text in available.items() if text}
        corrected = []
        for item in extraction.items:
            normalized_item = " ".join(item.text.casefold().split())
            item_words = set(re.findall(r"\w+", normalized_item))
            if not item_words:
                raise ValueError("O trecho extraído não contém texto verificável")

            def match_score(
                candidate: ClaimSource,
                words=item_words,
                text=normalized_item,
            ) -> tuple[float, float]:
                normalized_source = " ".join(available[candidate].casefold().split())
                source_words = set(re.findall(r"\w+", normalized_source))
                coverage = len(words & source_words) / len(words)
                similarity = SequenceMatcher(None, text, normalized_source).ratio()
                return coverage, similarity

            source = max(
                available,
                key=lambda candidate: match_score(candidate),
            )
            coverage, similarity = match_score(source)
            if coverage < 0.55 and similarity < 0.55:
                raise ValueError("O trecho extraído não está ancorado no contexto recebido")
            corrected.append(item.model_copy(update={"source": source}))
        return ClaimExtraction(items=corrected)

    async def _complete_validated(
        self, *, system, user, response_type, purpose, post_validate=None
    ):
        validation_error: Exception | None = None
        for attempt in range(2):
            retry_instruction = ""
            if attempt:
                retry_instruction = (
                    "\n\nSua resposta anterior falhou na validação. Gere novamente somente o JSON "
                    "e obedeça exatamente ao esquema, sem campos adicionais. "
                    f"Erro específico a corrigir: {validation_error}"
                )
            raw = await self.llm.complete(
                system=system + retry_instruction,
                user=user,
                json_mode=True,
                purpose=purpose,
            )
            try:
                result = response_type.model_validate_json(raw)
                if post_validate:
                    post_validate(result)
                return result
            except (ValidationError, ValueError) as exc:
                validation_error = exc
        raise StructuredLLMOutputError(
            f"Resposta inválida para {purpose} após 2 tentativas"
        ) from validation_error

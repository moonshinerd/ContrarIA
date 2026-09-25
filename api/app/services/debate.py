"""Serviço de Debate Multi-Agente (Promotor, Defensor, Juiz) com Humildade Epistêmica P(IK).

Implementa tribunal de verificação (arXiv:2510.12697 e Kadavath et al. arXiv:2207.05221):
- Promotor sustenta acusação embasada em evidências;
- Defensor aponta contexto, sátira, humor, ironia ou fragilidade probatória;
- Juiz pondera o debate e emite veredito JSON com calibração de certeza epistêmica P(IK);
- Em caso de dissidência severa ou P(IK) baixo, sinaliza abstenção (INSUFFICIENT_EVIDENCE).
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings
from app.domain.entities import Evidence, Verdict, VerdictLabel
from app.models.llm.base import LLMPort
from app.services.prompts_loader import load_prompt

logger = logging.getLogger(__name__)


@dataclass
class DebateTurn:
    """Registro de um turno de argumentação no debate."""

    round: int
    role: str  # "promotor" ou "defensor"
    argument: str
    cited_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class DebateVerdict:
    """Resultado estruturado do julgamento pelo Juiz."""

    claim: str
    label: VerdictLabel
    confidence: float
    rationale: str
    cited_evidence_ids: list[str]
    consensus: bool
    p_ik: float
    abstained: bool
    rounds_conducted: int
    transcript: list[DebateTurn] = field(default_factory=list)
    raw_judge_output: dict[str, Any] = field(default_factory=dict)

    def to_domain_verdict(self, evidences: list[Evidence]) -> Verdict:
        """Converte para a entidade de domínio Verdict."""
        agent_outputs: dict[str, str] = {}
        for turn in self.transcript:
            key = f"{turn.role}_r{turn.round}"
            agent_outputs[key] = turn.argument

        agent_outputs["juiz_rationale"] = self.rationale
        agent_outputs["consensus"] = str(self.consensus).lower()
        agent_outputs["p_ik"] = f"{self.p_ik:.4f}"

        return Verdict(
            claim=self.claim,
            label=self.label,
            confidence=self.confidence,
            rationale=self.rationale,
            evidences=evidences,
            agent_outputs=agent_outputs,
        )


class DebateService:
    """Orquestra o debate adversarial entre Promotor, Defensor e Juiz."""

    def __init__(self, llm: LLMPort, settings: Settings | None = None) -> None:
        self.llm = llm
        self.settings = settings or get_settings()

    def _format_evidences(self, evidences: list[Evidence]) -> tuple[str, dict[str, Evidence]]:
        """Formata as evidências indexando por identificadores determinísticos (ex: EV-01)."""
        if not evidences:
            return "Nenhuma evidência documental recuperada.", {}

        formatted_lines = []
        evidence_map: dict[str, Evidence] = {}
        for idx, ev in enumerate(evidences, start=1):
            ev_id = f"EV-{idx:02d}"
            evidence_map[ev_id] = ev
            rating_str = f" | Classificação: {ev.rating}" if ev.rating else ""
            line = (
                f"[{ev_id}] Fonte: {ev.source} | Título: {ev.title}{rating_str}\n"
                f"       Trecho: {ev.snippet}\n"
                f"       URL: {ev.url}"
            )
            formatted_lines.append(line)

        return "\n\n".join(formatted_lines), evidence_map

    def _extract_evidence_ids(self, text: str) -> list[str]:
        """Extrai IDs de evidências no formato EV-XX citados no texto."""
        matches = re.findall(r"\b(EV-\d+)\b", text, re.IGNORECASE)
        # Preserva a ordem e remove duplicatas
        seen = set()
        result = []
        for m in matches:
            upper = m.upper()
            if upper not in seen:
                seen.add(upper)
                result.append(upper)
        return result

    def _format_history(self, transcript: list[DebateTurn]) -> str:
        """Formata o histórico do debate para contextualização dos agentes."""
        if not transcript:
            return "Nenhuma rodada anterior realizada."

        blocks = []
        for turn in transcript:
            role_label = "PROMOTOR (Acusação)" if turn.role == "promotor" else "DEFENSOR (Defesa)"
            blocks.append(f"--- Rodada {turn.round}: {role_label} ---\n{turn.argument}")

        return "\n\n".join(blocks)

    def _clean_json_response(self, text: str) -> str:
        """Remove blocos de formatação markdown antes de fazer o parse JSON."""
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _parse_consensus(value: Any) -> bool:
        """Interpreta consenso sem tratar a string ``false`` como verdadeira."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "verdadeiro", "sim"}:
                return True
            if normalized in {"false", "falso", "não", "nao"}:
                return False
        return False

    async def conduct_debate(
        self,
        claim: str,
        post_text: str,
        evidences: list[Evidence],
        rounds: int | None = None,
        verified_answers: list[str] | None = None,
    ) -> DebateVerdict:
        """Executa as N rodadas de debate e emite o veredito final do Juiz."""
        num_rounds = rounds or self.settings.debate_rounds
        evidences_text, evidence_map = self._format_evidences(evidences)
        answers_text = (
            "\n".join(f"- {answer}" for answer in verified_answers)
            if verified_answers
            else "Nenhuma resposta verificada disponível."
        )

        promotor_prompt = load_prompt("promotor", version=1)
        defensor_prompt = load_prompt("defensor", version=1)
        juiz_prompt = load_prompt("juiz", version=1)

        transcript: list[DebateTurn] = []

        # Execução das N rodadas de debate
        for r in range(1, num_rounds + 1):
            # 1. Turno do Promotor
            history_text = self._format_history(transcript)
            promotor_input = (
                f"ALEGAÇÃO SOB JULGAMENTO:\n{claim}\n\n"
                f"TEXTO DA POSTAGEM ORIGINAL:\n{post_text}\n\n"
                f"EVIDÊNCIAS CATALOGADAS:\n{evidences_text}\n\n"
                f"RESPOSTAS VERIFICADAS PELO SELF-RAG:\n{answers_text}\n\n"
                f"HISTÓRICO DO DEBATE ATÉ O MOMENTO:\n{history_text}\n\n"
                f"Apresente seus argumentos para a Rodada {r}:"
            )
            promotor_arg = await self.llm.complete(
                system=promotor_prompt,
                user=promotor_input,
                role="promotor",
                purpose="debate",
            )
            cited_promotor = self._extract_evidence_ids(promotor_arg)
            transcript.append(
                DebateTurn(
                    round=r,
                    role="promotor",
                    argument=promotor_arg,
                    cited_evidence_ids=cited_promotor,
                )
            )

            # 2. Turno do Defensor
            history_text = self._format_history(transcript)
            defensor_input = (
                f"ALEGAÇÃO SOB JULGAMENTO:\n{claim}\n\n"
                f"TEXTO DA POSTAGEM ORIGINAL:\n{post_text}\n\n"
                f"EVIDÊNCIAS CATALOGADAS:\n{evidences_text}\n\n"
                f"RESPOSTAS VERIFICADAS PELO SELF-RAG:\n{answers_text}\n\n"
                f"HISTÓRICO DO DEBATE ATÉ O MOMENTO:\n{history_text}\n\n"
                f"Apresente seus contra-argumentos de defesa para a Rodada {r}:"
            )
            defensor_arg = await self.llm.complete(
                system=defensor_prompt,
                user=defensor_input,
                role="defensor",
                purpose="debate",
            )
            cited_defensor = self._extract_evidence_ids(defensor_arg)
            transcript.append(
                DebateTurn(
                    round=r,
                    role="defensor",
                    argument=defensor_arg,
                    cited_evidence_ids=cited_defensor,
                )
            )

        # 3. Julgamento do Juiz
        full_history = self._format_history(transcript)
        juiz_input = (
            f"ALEGAÇÃO SOB JULGAMENTO:\n{claim}\n\n"
            f"TEXTO DA POSTAGEM ORIGINAL:\n{post_text}\n\n"
            f"EVIDÊNCIAS CATALOGADAS:\n{evidences_text}\n\n"
            f"RESPOSTAS VERIFICADAS PELO SELF-RAG:\n{answers_text}\n\n"
            f"TRANSCRIÇÃO COMPLETA DAS {num_rounds} RODADAS DO DEBATE:\n{full_history}\n\n"
            "Emita seu veredito no formato JSON especificado:"
        )

        juiz_output = await self.llm.complete(
            system=juiz_prompt,
            user=juiz_input,
            json_mode=True,
            role="juiz",
            purpose="debate",
        )

        # Parse seguro do veredito do Juiz
        parsed: dict[str, Any] = {}
        try:
            cleaned = self._clean_json_response(juiz_output)
            parsed = json.loads(cleaned)
        except Exception as exc:
            logger.warning("Falha ao decodificar JSON do juiz: %s. Raw: %s", exc, juiz_output)
            parsed = {
                "label": "insufficient_evidence",
                "confidence": 0.5,
                "rationale": "Inconsistência estrutural na saída do juiz.",
                "cited_evidence_ids": [],
                "consensus": False,
                "p_ik": 0.0,
            }

        # Normalização dos campos
        raw_label = str(parsed.get("label", "insufficient_evidence")).strip().lower()
        if raw_label in ("true", "verdadeiro"):
            label = VerdictLabel.TRUE
        elif raw_label in ("false", "falso"):
            label = VerdictLabel.FALSE
        elif raw_label in ("misleading", "enganoso"):
            label = VerdictLabel.MISLEADING
        else:
            label = VerdictLabel.INSUFFICIENT_EVIDENCE

        confidence = float(parsed.get("confidence", 0.5))
        rationale = str(parsed.get("rationale", "")).strip()
        cited_ids = list(parsed.get("cited_evidence_ids", []))
        consensus = self._parse_consensus(parsed.get("consensus", False))
        p_ik = float(parsed.get("p_ik", confidence))

        # Aplicação da regra de Humildade Epistêmica P(IK).
        # "consensus" continua sendo registrado (é o autorrelato do juiz sobre
        # ter havido divergência não resolvida no debate), mas não bloqueia
        # mais sozinho: era um veto binário redundante sobre o próprio p_ik
        # (medida contínua e mais proporcional), e na prática abstinha mesmo
        # com p_ik alto (ex.: p_ik=0.9, consensus=false) -- calibrado a pedido
        # explícito (25/09/2026) para reduzir esse excesso de cautela.
        abstained = False
        if p_ik < self.settings.debate_p_ik_threshold:
            label = VerdictLabel.INSUFFICIENT_EVIDENCE
            abstained = True
            if not rationale:
                rationale = (
                    "Abstenção automática por baixa certeza epistêmica P(IK) "
                    "ou ausência de consenso."
                )

        return DebateVerdict(
            claim=claim,
            label=label,
            confidence=confidence,
            rationale=rationale,
            cited_evidence_ids=cited_ids,
            consensus=consensus,
            p_ik=p_ik,
            abstained=abstained,
            rounds_conducted=num_rounds,
            transcript=transcript,
            raw_judge_output=parsed,
        )

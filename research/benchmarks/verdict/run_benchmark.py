"""Executa o benchmark ao vivo ou recompõe tabelas de predições registradas."""

import argparse
import asyncio
import csv
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPOSITORY_ROOT / "api"
for import_root in (REPOSITORY_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from research.benchmarks.verdict.config import BenchmarkConfig, load_config  # noqa: E402
from research.benchmarks.verdict.dataset import BenchmarkClaim, load_claims  # noqa: E402
from research.benchmarks.verdict.leakage import is_origin_evidence  # noqa: E402
from research.benchmarks.verdict.metrics import group_metrics  # noqa: E402
from research.benchmarks.verdict.report import PREDICTION_COLUMNS, write_results  # noqa: E402
from research.benchmarks.verdict.scenarios import (  # noqa: E402
    AblationScenario,
    build_scenarios,
)


class _StaticCalibrations:
    def __init__(self, *, lambda_hat: float, alpha: float, model: str) -> None:
        from app.services.crc import CRCCalibration

        self.calibration = CRCCalibration(
            lambda_hat=lambda_hat,
            alpha=alpha,
            n=1,
            model=model,
            created_at=datetime.now(UTC),
        )

    def get_latest(self, model: str):
        return self.calibration if model == self.calibration.model else None


class _BenchmarkUsageTracker:
    """Mede apenas o custo desta execução, sem consultar ou gravar no banco."""

    def __init__(self) -> None:
        self.total_cost = 0.0

    def record(
        self,
        usage_date: date,
        model: str,
        purpose: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        self.total_cost += cost_usd

    def get_daily_cost(self, usage_date: date) -> float:
        return self.total_cost


class _LeakageFilteredSource:
    def __init__(self, wrapped, claim: BenchmarkClaim) -> None:
        self.wrapped = wrapped
        self.claim = claim
        self.name = wrapped.name

    async def search(self, query: str, *, limit: int = 5):
        candidates = await self.wrapped.search(query, limit=min(limit * 3, 20))
        return [
            evidence
            for evidence in candidates
            if not is_origin_evidence(
                evidence_url=evidence.url,
                title=evidence.title,
                snippet=evidence.snippet,
                origin_url=self.claim.review_url,
                publisher=self.claim.publisher,
            )
        ][:limit]


def _sources(settings, names: tuple[str, ...]):
    from app.clients.evidence import get_evidence_source
    from app.clients.evidence.google_factcheck import GoogleFactCheckClient

    result = []
    for name in names:
        if name == GoogleFactCheckClient.name:
            result.append(GoogleFactCheckClient(api_key=settings.google_factcheck_api_key))
        else:
            result.append(get_evidence_source(name, settings=settings))
    return result


async def _run_live(
    config: BenchmarkConfig,
    claims: list[BenchmarkClaim],
    scenarios: list[AblationScenario],
) -> list[dict[str, Any]]:
    from app.core.config import Settings
    from app.domain.entities import Post
    from app.models.llm.litellm_model import BudgetExceeded, LiteLLMModel
    from app.services.claim_verification import ClaimVerificationPlanner
    from app.services.debate import DebateService
    from app.services.self_rag import SelfRAGLimits, SelfRAGService
    from app.services.verification import VerificationService

    settings = Settings(
        llm_model_name=config.model,
        llm_model_prosecutor=config.model,
        llm_model_defender=config.model,
        llm_model_judge=config.model,
        crc_model_name=config.model,
        crc_alpha=config.alpha,
        debate_rounds=config.debate_rounds,
        debate_p_ik_threshold=config.p_ik_threshold,
    )
    tracker = _BenchmarkUsageTracker()
    llm = LiteLLMModel(settings=settings, tracker=tracker)
    calibrations = _StaticCalibrations(
        lambda_hat=config.lambda_hat,
        alpha=config.alpha,
        model=config.model,
    )
    predictions: list[dict[str, Any]] = []

    for scenario in scenarios:
        base_sources = _sources(settings, scenario.sources)
        for claim in claims:
            selected_sources = (
                [_LeakageFilteredSource(source, claim) for source in base_sources]
                if scenario.exclude_origin
                else base_sources
            )
            self_rag = SelfRAGService(
                llm,
                selected_sources,
                limits=SelfRAGLimits.from_settings(settings),
            )
            service = VerificationService(
                ClaimVerificationPlanner(llm),
                self_rag,
                DebateService(llm, settings),
                calibrations,
                settings=settings,
            )
            post = Post(
                uri=f"benchmark://claim/{claim.claim_id}",
                cid=claim.claim_id,
                author_did="did:benchmark:claimreview",
                text=claim.claim,
                created_at=datetime.combine(config.evaluation_date, datetime.min.time(), UTC),
                langs=["pt-BR"],
            )
            before_cost = tracker.total_cost
            started = perf_counter()
            error = ""
            try:
                verdict = await service.verify(post, current_date=config.evaluation_date)
                predicted_label = verdict.label.value
                confidence = verdict.confidence
                evidence_count = len(verdict.evidences)
            except BudgetExceeded:
                raise
            except Exception as exc:
                predicted_label = "insufficient_evidence"
                confidence = 0.0
                evidence_count = 0
                error = type(exc).__name__
            latency = perf_counter() - started
            predictions.append(
                {
                    "scenario": scenario.name,
                    "exclude_origin": scenario.exclude_origin,
                    "sources": "+".join(scenario.sources),
                    "claim_id": claim.claim_id,
                    "expected_label": claim.expected_label,
                    "predicted_label": predicted_label,
                    "confidence": confidence,
                    "latency_seconds": latency,
                    "cost_usd": tracker.total_cost - before_cost,
                    "evidence_count": evidence_count,
                    "error": error,
                }
            )
            print(
                f"[{scenario.name}] {claim.claim_id}: "
                f"{claim.expected_label} -> {predicted_label} ({latency:.2f}s)"
            )
    return predictions


def _read_predictions(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["exclude_origin"] = str(row["exclude_origin"]).casefold() in {"1", "true", "sim"}
        for key in ("confidence", "latency_seconds", "cost_usd"):
            row[key] = float(row[key])
        row["evidence_count"] = int(row["evidence_count"])
    return rows


def _validate_predictions(
    rows: list[dict[str, Any]],
    claims: list[BenchmarkClaim],
    scenarios: list[AblationScenario],
) -> None:
    expected = {
        (scenario.name, scenario.exclude_origin, claim.claim_id)
        for scenario in scenarios
        for claim in claims
    }
    received = {
        (str(row["scenario"]), bool(row["exclude_origin"]), str(row["claim_id"])) for row in rows
    }
    if len(received) != len(rows):
        raise ValueError("Predições registradas contêm chaves duplicadas")
    missing = expected - received
    extra = received - expected
    if missing or extra:
        raise ValueError(
            f"Predições não correspondem à configuração: faltam={len(missing)}, sobram={len(extra)}"
        )
    expected_by_claim = {claim.claim_id: claim.expected_label for claim in claims}
    sources_by_scenario = {
        (scenario.name, scenario.exclude_origin): "+".join(scenario.sources)
        for scenario in scenarios
    }
    for row in rows:
        if str(row["predicted_label"]) not in {
            "false",
            "misleading",
            "true",
            "insufficient_evidence",
        }:
            raise ValueError(f"Rótulo predito inválido: {row['predicted_label']}")
        if row["expected_label"] != expected_by_claim[row["claim_id"]]:
            raise ValueError(f"Rótulo esperado diverge do dataset: {row['claim_id']}")
        scenario_key = (str(row["scenario"]), bool(row["exclude_origin"]))
        if row["sources"] != sources_by_scenario[scenario_key]:
            raise ValueError(f"Fontes divergem do cenário: {row['scenario']}")
        if not 0 <= float(row["confidence"]) <= 1:
            raise ValueError(f"Confiança inválida: {row['confidence']}")
        if float(row["latency_seconds"]) < 0 or float(row["cost_usd"]) < 0:
            raise ValueError("Latência e custo devem ser não negativos")
        if list(row) != PREDICTION_COLUMNS:
            # DictReader preserva o cabeçalho; exigir o contrato evita resultados ambíguos.
            raise ValueError("CSV de predições não segue o cabeçalho esperado")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Recalcula tabelas de um CSV registrado, sem chamadas externas",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = load_config(args.config.resolve(), REPOSITORY_ROOT)
    claims = load_claims(
        config.dataset,
        calibration_path=config.calibration_dataset,
        limit=config.max_claims,
    )
    scenarios = build_scenarios(
        config.sources,
        include_all=config.include_all,
        individual=config.individual,
        leave_one_out=config.leave_one_out,
        repeat_without_origin=config.repeat_without_origin,
    )
    if args.predictions:
        predictions = _read_predictions(args.predictions.resolve())
        execution = "replay"
    else:
        predictions = asyncio.run(_run_live(config, claims, scenarios))
        execution = "live"
    _validate_predictions(predictions, claims, scenarios)
    metrics = group_metrics(predictions)
    write_results(
        config.output_dir,
        predictions,
        metrics,
        metadata={
            "execution": execution,
            "config": str(args.config),
            "dataset": str(config.dataset),
            "model": config.model,
            "evaluation_date": config.evaluation_date.isoformat(),
            "lambda_hat": config.lambda_hat,
            "alpha": config.alpha,
            "claims": len(claims),
            "scenarios": len(scenarios),
        },
    )
    print(f"Resultados gravados em {config.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

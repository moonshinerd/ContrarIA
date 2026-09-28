"""Leitura da configuração YAML do benchmark."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BenchmarkConfig:
    dataset: Path
    calibration_dataset: Path | None
    output_dir: Path
    model: str
    evaluation_date: date
    lambda_hat: float
    alpha: float
    max_claims: int | None
    sources: list[str]
    include_all: bool
    individual: bool
    leave_one_out: bool
    repeat_without_origin: bool
    debate_rounds: int
    p_ik_threshold: float


def _resolve_path(repo_root: Path, value: Any, *, required: bool) -> Path | None:
    if value in (None, ""):
        if required:
            raise ValueError("Caminho obrigatório ausente na configuração")
        return None
    path = Path(str(value))
    return path if path.is_absolute() else repo_root / path


def load_config(path: Path, repo_root: Path) -> BenchmarkConfig:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("A configuração YAML deve ser um objeto")

    ablation = payload.get("ablation", {})
    runtime = payload.get("runtime", {})
    sources = list(payload.get("sources", []))
    if not all(isinstance(item, str) and item for item in sources):
        raise ValueError("sources deve ser uma lista de nomes não vazios")

    lambda_hat = float(payload.get("lambda_hat", -1))
    alpha = float(payload.get("alpha", 0.05))
    if lambda_hat < 0 or not 0 < alpha < 1:
        raise ValueError("lambda_hat deve ser não negativo e alpha deve estar em (0, 1)")

    model = str(payload.get("model", "")).strip()
    if not model:
        raise ValueError("model é obrigatório")

    return BenchmarkConfig(
        dataset=_resolve_path(repo_root, payload.get("dataset"), required=True),
        calibration_dataset=_resolve_path(
            repo_root, payload.get("calibration_dataset"), required=False
        ),
        output_dir=_resolve_path(repo_root, payload.get("output_dir"), required=True),
        model=model,
        evaluation_date=date.fromisoformat(str(payload.get("evaluation_date", ""))),
        lambda_hat=lambda_hat,
        alpha=alpha,
        max_claims=int(payload["max_claims"]) if payload.get("max_claims") else None,
        sources=sources,
        include_all=bool(ablation.get("include_all", True)),
        individual=bool(ablation.get("individual", True)),
        leave_one_out=bool(ablation.get("leave_one_out", True)),
        repeat_without_origin=bool(ablation.get("repeat_without_origin", True)),
        debate_rounds=int(runtime.get("debate_rounds", 1)),
        p_ik_threshold=float(runtime.get("p_ik_threshold", 0.60)),
    )

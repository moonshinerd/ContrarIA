"""Calibração de Conformal Risk Control para decisões de verificação."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, nextafter

ADVERSE_LABELS = frozenset({"false", "misleading"})
TRUE_LABEL = "true"
KNOWN_LABELS = frozenset({TRUE_LABEL, *ADVERSE_LABELS, "insufficient_evidence"})


@dataclass(frozen=True)
class CalibrationExample:
    """Predição rotulada usada para estimar o limiar CRC."""

    actual_label: str
    predicted_label: str
    confidence: float
    sample_id: str = ""

    def __post_init__(self) -> None:
        if self.actual_label.casefold() not in KNOWN_LABELS - {"insufficient_evidence"}:
            raise ValueError(f"actual_label inválido: {self.actual_label}")
        if self.predicted_label.casefold() not in KNOWN_LABELS:
            raise ValueError(f"predicted_label inválido: {self.predicted_label}")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence deve estar no intervalo [0, 1]")


@dataclass(frozen=True)
class CalibrationResult:
    """Limiar e métricas que demonstram a garantia obtida."""

    lambda_hat: float
    alpha: float
    n: int
    empirical_risk: float
    risk_bound: float
    false_positives: int
    true_examples: int

    @property
    def conditional_false_positive_rate(self) -> float:
        if self.true_examples == 0:
            return 0.0
        return self.false_positives / self.true_examples


@dataclass(frozen=True)
class CRCCalibration:
    """Calibração persistida e consumida pelo runtime."""

    lambda_hat: float
    alpha: float
    n: int
    model: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isfinite(self.lambda_hat) or self.lambda_hat < 0:
            raise ValueError("lambda_hat deve ser finito e não negativo")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha deve estar no intervalo (0, 1)")
        if self.n <= 0:
            raise ValueError("n deve ser positivo")
        if not self.model.strip():
            raise ValueError("model é obrigatório")


def _is_false_positive(example: CalibrationExample, threshold: float) -> bool:
    return (
        example.actual_label.casefold() == TRUE_LABEL
        and example.predicted_label.casefold() in ADVERSE_LABELS
        and example.confidence >= threshold
    )


def calibrate_threshold(
    examples: list[CalibrationExample],
    *,
    alpha: float = 0.05,
    bound: float = 1.0,
) -> CalibrationResult:
    """Calcula o menor limiar observável cuja cota CRC não supera ``alpha``.

    A perda vale 1 quando uma alegação verdadeira recebe um rótulo adverso
    (``false`` ou ``misleading``) acima do limiar de atuação.
    """
    if not examples:
        raise ValueError("A calibração exige ao menos uma amostra")
    if not 0 < alpha < 1:
        raise ValueError("alpha deve estar no intervalo (0, 1)")
    if bound <= 0:
        raise ValueError("bound deve ser positivo")

    n = len(examples)
    # nextafter mantém a regra de runtime estritamente '< lambda_hat' segura
    # quando uma confiança observada coincide com o ponto de corte.
    candidates = {0.0}
    candidates.update(nextafter(item.confidence, float("inf")) for item in examples)

    true_examples = sum(item.actual_label.casefold() == TRUE_LABEL for item in examples)
    for threshold in sorted(candidates):
        false_positives = sum(_is_false_positive(item, threshold) for item in examples)
        empirical_risk = false_positives / n
        risk_bound = (n / (n + 1)) * empirical_risk + bound / (n + 1)
        if risk_bound <= alpha + 1e-12:
            return CalibrationResult(
                lambda_hat=threshold,
                alpha=alpha,
                n=n,
                empirical_risk=empirical_risk,
                risk_bound=risk_bound,
                false_positives=false_positives,
                true_examples=true_examples,
            )

    minimum = bound / (n + 1)
    raise ValueError(
        "Nenhum limiar satisfaz a garantia CRC: "
        f"a cota mínima {minimum:.6f} excede alpha={alpha:.6f}. "
        "Use mais amostras de calibração."
    )

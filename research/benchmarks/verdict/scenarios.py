"""Geração determinística das configurações de ablação."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AblationScenario:
    name: str
    sources: tuple[str, ...]
    exclude_origin: bool


def build_scenarios(
    sources: list[str],
    *,
    include_all: bool = True,
    individual: bool = True,
    leave_one_out: bool = True,
    repeat_without_origin: bool = True,
) -> list[AblationScenario]:
    if not sources or len(sources) != len(set(sources)):
        raise ValueError("sources deve conter nomes únicos e não pode ser vazio")

    base: list[tuple[str, tuple[str, ...]]] = []
    if include_all:
        base.append(("all", tuple(sources)))
    if individual:
        base.extend((f"only_{source}", (source,)) for source in sources)
    if leave_one_out:
        base.extend(
            (f"without_{source}", tuple(item for item in sources if item != source))
            for source in sources
        )

    scenarios: list[AblationScenario] = []
    for name, selected in base:
        scenarios.append(AblationScenario(name=name, sources=selected, exclude_origin=False))
        if repeat_without_origin and "google_factcheck" in selected:
            scenarios.append(
                AblationScenario(
                    name=f"{name}_no_origin",
                    sources=selected,
                    exclude_origin=True,
                )
            )
    return scenarios

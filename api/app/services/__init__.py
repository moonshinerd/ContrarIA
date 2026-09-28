"""Serviços de aplicação do ContrarIA."""

from app.services.debate import DebateService, DebateTurn, DebateVerdict

__all__ = ["DebateService", "DebateTurn", "DebateVerdict", "VerificationService"]


def __getattr__(name: str):
    """Carrega o orquestrador sob demanda para evitar ciclos com repositórios."""
    if name == "VerificationService":
        from app.services.verification import VerificationService

        return VerificationService
    raise AttributeError(name)

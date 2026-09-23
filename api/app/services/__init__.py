"""Serviços de aplicação do ContrarIA."""

from app.services.debate import DebateService, DebateTurn, DebateVerdict
from app.services.verification import VerificationService

__all__ = ["DebateService", "DebateTurn", "DebateVerdict", "VerificationService"]

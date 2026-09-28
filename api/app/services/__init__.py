"""Serviços de aplicação do ContrarIA."""

from app.services.debate import DebateService, DebateTurn, DebateVerdict

__all__ = [
    "DebateService",
    "DebateTurn",
    "DebateVerdict",
    "VerificationService",
    "build_verification_service",
]


def __getattr__(name: str):
    """Carrega o orquestrador sob demanda para evitar ciclos com repositórios."""
    if name == "VerificationService":
        from app.services.verification import VerificationService

        return VerificationService
    raise AttributeError(name)


def build_verification_service(llm, settings=None, engine=None):
    """Escolhe o backend de verificação conforme `settings.verification_backend`.

    "llm" (padrão): CoVe + Self-RAG + debate multiagente na nuvem, calibrado.
    "jev": classificação local via logprobs, sem gerar JSON; o LLM continua
    sendo usado depois só pra escrever o texto da intervenção (ver
    intervention.py), não pra decidir o veredito.
    """
    from app.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.verification_backend == "jev":
        from app.services.jev_verification import JevVerificationService

        return JevVerificationService.from_settings(settings=resolved, engine=engine)

    from app.services.verification import VerificationService

    return VerificationService.from_settings(llm, settings=resolved, engine=engine)

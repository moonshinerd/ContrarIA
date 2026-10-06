"""Endpoint de deploy autenticado pela identidade do GitHub Actions (token OIDC).

A VM de produção não recebe conexões de entrada; o único caminho de deploy que chega até ela é este
endpoint, publicado por túnel (ADR 0020). Ele só aceita um token JWT emitido pelo GitHub para **este
repositório**, na **branch main**, pelo workflow `deploy.yml` e pelo environment `production`.
Qualquer outra coisa recebe 401.

O serviço não executa o deploy: apenas grava um arquivo de gatilho num diretório compartilhado com
o host, onde um serviço do systemd (usuário `deploy`) roda o script de deploy. O endpoint não recebe
comandos nem parâmetros e o deploy sempre usa a `origin/main`. Roda num container sem o `.env` da
aplicação, sem root e sem acesso ao Docker.
"""

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import jwt
from fastapi import FastAPI, Header, HTTPException

logger = logging.getLogger("contraria.deployhook")

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks"
MAX_TOKEN_CHARS = 8192


@dataclass(frozen=True)
class HookConfig:
    audience: str = "contraria-deploy"
    repository: str = "moonshinerd/ContrarIA"
    # IDs numéricos: o nome do repositório pode ser reaproveitado após uma renomeação ou exclusão.
    repository_id: str = "1362706807"
    owner_id: str = "121871105"
    ref: str = "refs/heads/main"
    workflow_ref: str = "moonshinerd/ContrarIA/.github/workflows/deploy.yml@refs/heads/main"
    environment: str = "production"
    trigger_dir: Path = Path("/var/lib/contraria-deploy")
    max_token_age_s: int = 600
    min_interval_s: int = 20


def load_config() -> HookConfig:
    base = HookConfig()
    return HookConfig(
        audience=os.environ.get("DEPLOYHOOK_AUDIENCE", base.audience),
        repository=os.environ.get("DEPLOYHOOK_REPOSITORY", base.repository),
        repository_id=os.environ.get("DEPLOYHOOK_REPOSITORY_ID", base.repository_id),
        owner_id=os.environ.get("DEPLOYHOOK_OWNER_ID", base.owner_id),
        ref=os.environ.get("DEPLOYHOOK_REF", base.ref),
        workflow_ref=os.environ.get("DEPLOYHOOK_WORKFLOW_REF", base.workflow_ref),
        environment=os.environ.get("DEPLOYHOOK_ENVIRONMENT", base.environment),
        trigger_dir=Path(os.environ.get("DEPLOYHOOK_DIR", str(base.trigger_dir))),
    )


class Unauthorized(Exception):
    """Token ausente, inválido ou de outra origem. O motivo vai só para o log."""


KeyProvider = Callable[[str], object]


def github_key_provider() -> KeyProvider:
    """Chave pública de assinatura do GitHub (JWKS), com cache; escolhe a chave pelo `kid`."""
    client = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)

    def provide(token: str) -> object:
        return client.get_signing_key_from_jwt(token).key

    return provide


def verify_token(token: str, cfg: HookConfig, key_provider: KeyProvider) -> dict:
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise Unauthorized("token ausente ou grande demais")
    try:
        key = key_provider(token)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],  # só RS256: impede "none" e a troca por HS256
            audience=cfg.audience,
            issuer=ISSUER,
            leeway=30,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except Exception as exc:  # PyJWTError, falha de rede no JWKS, kid desconhecido...
        raise Unauthorized(f"token inválido ({type(exc).__name__})") from exc

    age = time.time() - float(claims["iat"])
    if age > cfg.max_token_age_s or age < -30:
        raise Unauthorized("token fora da janela de emissão")

    expected = {
        "repository": cfg.repository,
        "repository_id": cfg.repository_id,
        "repository_owner_id": cfg.owner_id,
        "ref": cfg.ref,
        "job_workflow_ref": cfg.workflow_ref,
        "environment": cfg.environment,
    }
    for name, value in expected.items():
        if str(claims.get(name)) != value:
            raise Unauthorized(f"claim {name} diferente do esperado")
    if claims.get("event_name") not in ("push", "workflow_dispatch"):
        raise Unauthorized("evento não permitido")
    return claims


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def create_app(cfg: HookConfig | None = None, key_provider: KeyProvider | None = None) -> FastAPI:
    cfg = cfg or load_config()
    provider = key_provider or github_key_provider()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authenticate(authorization: str | None) -> dict:
        try:
            return verify_token(_bearer(authorization), cfg, provider)
        except Unauthorized as exc:
            logger.warning("acesso negado: %s", exc)
            raise HTTPException(status_code=401, detail="unauthorized") from None

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/deploy", status_code=202)
    def deploy(authorization: str | None = Header(default=None)) -> dict:
        claims = authenticate(authorization)
        trigger = cfg.trigger_dir / "trigger"
        now = time.time()
        requested_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        # um gatilho recente basta: o deploy sempre usa a origin/main e vários pedidos viram um
        if trigger.exists() and now - trigger.stat().st_mtime < cfg.min_interval_s:
            return {"status": "already_queued", "requested_at": requested_at}
        payload = {
            "requested_at": requested_at,
            "sha": claims.get("sha"),
            "run_id": claims.get("run_id"),
            "actor": claims.get("actor"),
        }
        tmp = cfg.trigger_dir / f".trigger.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, trigger)
        logger.info("deploy enfileirado (run %s, sha %s)", claims.get("run_id"), claims.get("sha"))
        return {"status": "queued", "requested_at": requested_at}

    @app.get("/status")
    def status(authorization: str | None = Header(default=None)) -> dict:
        authenticate(authorization)
        try:
            return json.loads((cfg.trigger_dir / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"state": "unknown"}

    return app


# `uvicorn app.deployhook:app` (o container de produção usa este objeto)
app = create_app()

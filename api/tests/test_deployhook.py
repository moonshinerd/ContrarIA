import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64encode

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.deployhook import ISSUER, HookConfig, create_app

CFG_KW = dict(
    audience="contraria-deploy",
    repository="moonshinerd/ContrarIA",
    repository_id="1362706807",
    owner_id="121871105",
    ref="refs/heads/main",
    workflow_ref="moonshinerd/ContrarIA/.github/workflows/deploy.yml@refs/heads/main",
    environment="production",
)


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def setup(tmp_path, keypair):
    private, public = keypair
    cfg = HookConfig(trigger_dir=tmp_path, **CFG_KW)
    client = TestClient(create_app(cfg, key_provider=lambda token: public))

    def token(**over):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": "contraria-deploy",
            "sub": "repo:moonshinerd/ContrarIA:environment:production",
            "iat": now,
            "exp": now + 300,
            "repository": "moonshinerd/ContrarIA",
            "repository_id": "1362706807",
            "repository_owner_id": "121871105",
            "ref": "refs/heads/main",
            "job_workflow_ref": CFG_KW["workflow_ref"],
            "environment": "production",
            "event_name": "push",
            "sha": "abc123",
            "run_id": "42",
            "actor": "moonshinerd",
        }
        claims.update(over)
        return jwt.encode(
            {k: v for k, v in claims.items() if v is not None}, private, algorithm="RS256"
        )

    return client, tmp_path, token


def post(client, tok):
    return client.post("/deploy", headers={"Authorization": f"Bearer {tok}"})


def test_token_valido_enfileira_o_deploy(setup):
    client, d, token = setup
    r = post(client, token())
    assert r.status_code == 202 and r.json()["status"] == "queued"
    payload = json.loads((d / "trigger").read_text())
    assert payload["sha"] == "abc123" and payload["run_id"] == "42"


@pytest.mark.parametrize(
    "over",
    [
        {"repository": "atacante/ContrarIA"},
        {"repository_id": "1"},  # repositório renomeado/recriado com o mesmo nome
        {"repository_owner_id": "1"},
        {"ref": "refs/heads/feature/x"},
        {"ref": "refs/pull/1/merge"},
        {"job_workflow_ref": "moonshinerd/ContrarIA/.github/workflows/ci.yml@refs/heads/main"},
        {"environment": None},
        {"environment": "staging"},
        {"event_name": "pull_request"},
        {"aud": "outra-coisa"},
        {"iss": "https://evil.example.com"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 3700},
        {"iat": int(time.time()) - 3000, "exp": int(time.time()) + 300},  # emitido há tempo demais
    ],
)
def test_tokens_de_outra_origem_sao_recusados(setup, over):
    client, d, token = setup
    r = post(client, token(**over))
    assert r.status_code == 401 and r.json() == {"detail": "unauthorized"}
    assert not (d / "trigger").exists()


def test_token_assinado_com_outra_chave_e_recusado(setup):
    client, d, _ = setup
    outra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    tok = jwt.encode(
        {"iss": ISSUER, "aud": "contraria-deploy", "sub": "x", "iat": now, "exp": now + 60},
        outra,
        algorithm="RS256",
    )
    assert post(client, tok).status_code == 401
    assert not (d / "trigger").exists()


def _b64(raw: bytes) -> bytes:
    return urlsafe_b64encode(raw).rstrip(b"=")


def test_alg_none_e_confusao_hs256_sao_recusados(setup, keypair):
    client, d, _ = setup
    _, public = keypair
    now = int(time.time())
    base = {"iss": ISSUER, "aud": "contraria-deploy", "sub": "x", "iat": now, "exp": now + 60}

    # "alg: none": token sem assinatura
    assert post(client, jwt.encode(base, key=None, algorithm="none")).status_code == 401

    # confusão de algoritmo: HS256 com a chave PÚBLICA como segredo (montado à mão, pois o PyJWT
    # se recusa a assinar assim). O serviço só aceita RS256.
    pem = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(base).encode())
    sig = _b64(hmac.new(pem, head + b"." + body, hashlib.sha256).digest())
    assert post(client, (head + b"." + body + b"." + sig).decode()).status_code == 401
    assert not (d / "trigger").exists()


@pytest.mark.parametrize(
    "auth", [None, "", "Bearer", "Bearer ", "Basic abc", "Bearer lixo", "Bearer " + "a" * 9000]
)
def test_sem_token_valido_nao_passa(setup, auth):
    client, d, _ = setup
    headers = {} if auth is None else {"Authorization": auth}
    assert client.post("/deploy", headers=headers).status_code == 401
    assert not (d / "trigger").exists()


def test_pedidos_repetidos_viram_um_so(setup):
    client, d, token = setup
    assert post(client, token()).json()["status"] == "queued"
    assert post(client, token()).json()["status"] == "already_queued"


def test_status_exige_token_e_devolve_o_ultimo_resultado(setup):
    client, d, token = setup
    assert client.get("/status").status_code == 401
    h = {"Authorization": f"Bearer {token()}"}
    assert client.get("/status", headers=h).json() == {"state": "unknown"}
    (d / "status.json").write_text(json.dumps({"state": "ok", "sha": "abc"}))
    assert client.get("/status", headers=h).json()["state"] == "ok"


def test_health_e_publico_e_nao_ha_docs(setup):
    client, _, _ = setup
    assert client.get("/health").json() == {"status": "ok"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404

# deploy/

Produção: `docker-compose.prod.yml` + `Caddyfile` (HTTPS automático, DNS na
Cloudflare) + Ozone (labeler). A aplicação também exige o serviço `jev`, que
executa localmente o Qwen3-4B GGUF via `llama.cpp`; API e worker devem apontar
`JEV_SERVER_URL` para ele e nunca carregar cópias próprias do modelo.

## Backend Jev

Use uma VPS com ao menos 4 vCPU, 8 GB de RAM e 40 GB de SSD para a pilha essencial (db, jev, searxng, api, worker); para folga operacional e inclusão do Ozone (labeler), a recomendação é 8 vCPU, 16 GB de RAM e 60 a 80 GB de SSD. Configure
`VERIFICATION_BACKEND=jev`, `JEV_MODEL_REPO`, `JEV_MODEL_FILE` e
`JEV_SERVER_URL`. Mantenha `JEV_ALLOW_UNCALIBRATED=false`: o banco deve conter
a calibração CRC para a chave do modelo antes de o worker poder publicar.

O guia de reprodução e seed da calibração está em
[`docs/calibracao-jev.md`](../docs/calibracao-jev.md). O LLM configurado ainda
é necessário apenas para redigir o quote post depois da decisão local.

## Ozone / Labeler

Antes do primeiro `docker compose up`, crie uma conta Bluesky exclusiva para o
labeler e preencha no `.env` do servidor: `OZONE_LABELER_DID`,
`OZONE_ADMIN_PASSWORD`, `OZONE_SIGNING_KEY_HEX` e `OZONE_POSTGRES_PASSWORD`.
O `OZONE_DOMAIN` deve apontar para a VPS antes da subida. Depois, entre em
`https://$OZONE_DOMAIN`, conclua o anúncio do serviço no DID e publique o record
`app.bsky.labeler.service` com `cd api && uv run python -m scripts.setup_labeler`.

Mantenha `PIPELINE_LABELER_ENABLED=false` até testar um post autorizado; a
emissão de rótulos é deliberadamente opt-in.

O procedimento completo, incluindo geração de segredos, anúncio no DID e teste
de emissão/reversão, está em [OZONE_RUNBOOK.md](OZONE_RUNBOOK.md).

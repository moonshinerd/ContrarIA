# deploy/

Produção: `docker-compose.prod.yml` + `Caddyfile` (HTTPS automático, DNS na Cloudflare) + Ozone (labeler). Implementado nas issues de deploy e de labeler.

## Ozone / Labeler

Antes do primeiro `docker compose up`, crie uma conta Bluesky exclusiva para o
labeler e preencha no `.env` do servidor: `OZONE_LABELER_DID`,
`OZONE_ADMIN_PASSWORD`, `OZONE_SIGNING_KEY_HEX` e `OZONE_POSTGRES_PASSWORD`.
O `OZONE_DOMAIN` deve apontar para a VPS antes da subida. Depois, entre em
`https://$OZONE_DOMAIN`, conclua o anúncio do serviço no DID e publique o record
`app.bsky.labeler.service` com `python api/scripts/setup_labeler.py`.

Mantenha `PIPELINE_LABELER_ENABLED=false` até testar um post autorizado; a
emissão de rótulos é deliberadamente opt-in.

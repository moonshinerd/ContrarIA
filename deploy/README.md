# deploy/

Produção: `docker-compose.prod.yml` + Ozone (labeler). A VM não recebe conexões de
entrada: o acesso externo (Ozone e deploy) passa por um túnel Cloudflare, publicado
por SSH reverso (ver [ADR 0020](../docs/adr/0020-acesso-vm-tunel-cloudflare.md)). A aplicação também exige o serviço `jev`, que
executa localmente o modelo mDeBERTa-v3 NLI via PyTorch/Transformers; API e worker devem apontar
`JEV_SERVER_URL` para ele e nunca carregar cópias próprias do modelo.

## Acesso e deploy (Cloudflare)

- **Ozone:** `https://contraria.schmidt.monster` → túnel `contraria-vm` → `localhost:3000`.
- **Deploy:** push na `main` dispara `.github/workflows/deploy.yml` (ambiente `production`). O workflow se autentica
  com o token OIDC do GitHub e chama `https://deploy-contraria.schmidt.monster/deploy`; o endpoint
  (`api/app/deployhook.py`) só aceita este repositório, a branch `main` e o workflow `deploy.yml`, e apenas grava um
  gatilho. O serviço systemd `contraria-deploy-hook` roda o script de deploy (`git reset` na `main`,
  `docker compose up -d --build`, `alembic upgrade head`). Não há chave SSH nem segredo no GitHub; a única variável do
  ambiente `production` é `DEPLOY_URL`.
- **SSH da VM:** não é publicado. Acesso só pela rede local ou VPN.
- **Na VM:** `api/.env` em `/opt/contraria/api/.env` (permissão 600, fora do git).
- **Scripts da VM** em `deploy/vm/`: `contraria-deploy.sh`, `contraria-deploy-run.sh` + unidades `contraria-deploy-hook.{path,service}` (executam o deploy
  pedido pelo endpoint) e a limpeza do Docker (`contraria-docker-prune.sh` + timer semanal), instalados em `/opt/` com dono `root`. Os logs dos containers têm
  rotação no compose. Veja [Operação na VM](../docs/arquitetura/operacao-vm.md#disco-e-cache-do-docker).

## Backend Jev

Use uma VPS com ao menos 4 vCPU, 8 GB de RAM e 40 GB de SSD para a pilha essencial (db, jev, searxng, api, worker); para folga operacional e inclusão do Ozone (labeler), a recomendação é 8 vCPU, 16 GB de RAM e 60 a 80 GB de SSD. Configure
`VERIFICATION_BACKEND=jev`, `JEV_MODEL_REPO` e
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

A emissão de rótulos é opt-in (`PIPELINE_LABELER_ENABLED`). Na VM de produção ela está **ligada** desde 05/10/2026,
com `INTERVENTION_DRY_RUN=false` (veja [Operação na VM](../docs/arquitetura/operacao-vm.md#producao-ligada-05102026)).

O procedimento completo, incluindo geração de segredos, anúncio no DID e teste
de emissão/reversão, está em [OZONE_RUNBOOK.md](OZONE_RUNBOOK.md).

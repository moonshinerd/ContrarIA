# Runbook — Ozone Labeler

Este guia é a sequência operacional para ativar o Labeler do ContrarIA em
produção. A conta Bluesky do Labeler é distinta da conta que publica quotes.

## Estado já concluído

- Conta de serviço criada: `contraria-labeler.bsky.social`.
- O DID dessa conta deve estar em `OZONE_LABELER_DID` no `.env` do servidor.
- O record `app.bsky.labeler.service` já declara `possivel-desinformacao`,
  `provavel-bot` e `evidencia-insuficiente`.
- A App Password da conta Labeler deve ficar somente em
  `OZONE_LABELER_APP_PASSWORD`; nunca em Git, logs ou mensagens.

## Pré-requisitos da VPS

1. VPS Linux com Docker Compose, portas TCP 80 e 443 abertas.
2. Registro DNS `ozone.<domínio>` apontando para o IP público da VPS.
3. `API_DOMAIN` e `OZONE_DOMAIN` definidos no `.env` exclusivo do servidor.
4. Copiar o `.env` local apenas por canal seguro e restringir permissões:
   `chmod 600 api/.env`.

## Segredos para gerar no servidor

Não reutilize senha da conta Bluesky. Gere valores independentes e adicione-os
ao `api/.env` do servidor:

```sh
openssl rand -hex 32 # OZONE_ADMIN_PASSWORD
openssl rand -hex 32 # OZONE_POSTGRES_PASSWORD
openssl ecparam --name secp256k1 --genkey --noout --outform DER \
  | tail --bytes=+8 | head --bytes=32 | xxd --plain --cols 32
  # OZONE_SIGNING_KEY_HEX
```

Também defina `OZONE_POSTGRES_USER=postgres` e `OZONE_POSTGRES_DB=ozone`.

## Subida e anúncio do serviço

1. Na VPS, execute `docker compose -f deploy/docker-compose.prod.yml up -d`.
2. Confirme a saúde: `curl --fail https://$OZONE_DOMAIN/xrpc/_health`.
3. Abra `https://$OZONE_DOMAIN` e entre como a conta Labeler usando sua App
   Password. O assistente do Ozone anuncia o serviço no DID, adicionando o
   endpoint e a chave de verificação exigidos pelo AT Protocol.
4. Rode novamente, de forma idempotente, o setup dos valores de rótulo:

   ```sh
   cd api && uv run python -m scripts.setup_labeler
   ```

## Teste de emissão seguro

1. Crie um post de teste autorizado na própria conta Labeler ou em outra conta
   de teste controlada pela equipe; guarde a URL, URI e CID.
2. Mantenha `INTERVENTION_DRY_RUN=true` e habilite apenas
   `PIPELINE_LABELER_ENABLED=true` após o Ozone estar saudável.
3. Execute a análise contra o post de teste e confirme no Ozone e no app
   Bluesky que o rótulo aparece.
4. Faça a revisão com `review_action=reverter` e confirme que o evento de
   negação remove o rótulo sem alterar a decisão original.
5. Volte `PIPELINE_LABELER_ENABLED=false` se o ambiente ainda for de teste.

Nunca aplique ou remova rótulos de posts de terceiros sem uma revisão humana e
uma autorização explícita para aquele post.

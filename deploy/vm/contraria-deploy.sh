#!/bin/bash
# Único comando que a chave do GitHub Actions pode executar (command= no authorized_keys do usuário
# `deploy`). Instalado como /opt/contraria-deploy.sh, de propriedade do root.
set -euo pipefail
cd /opt/contraria
BRANCH="${DEPLOY_BRANCH:-main}"
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file api/.env"
$COMPOSE up -d --build --remove-orphans
$COMPOSE exec -T api alembic upgrade head
$COMPOSE ps
/opt/contraria-docker-prune.sh || echo "aviso: a limpeza do Docker falhou (o deploy foi concluído)"

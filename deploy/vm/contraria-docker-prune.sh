#!/bin/bash
# Limpeza segura do Docker na VM. NUNCA remove volumes (bancos, cache do modelo, sessão do bot).
# Chamado no fim de cada deploy e por um timer semanal (contraria-docker-prune.timer).
set -euo pipefail

docker image prune -f >/dev/null                          # camadas órfãs de builds anteriores
docker builder prune -f --filter "until=168h" >/dev/null  # cache de build com mais de 7 dias

USED=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "$USED" -ge 80 ]; then
  echo "disco em ${USED}%: limpeza agressiva (cache de build e imagens sem container)"
  docker builder prune -af >/dev/null
  docker image prune -af >/dev/null                       # só imagens que nenhum container usa
fi
echo "disco: $(df --output=pcent / | tail -1 | tr -d ' ') usado"

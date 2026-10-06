#!/bin/bash
# Executa o deploy quando o endpoint (container `deployhook`) grava o gatilho. Roda como usuário `deploy`,
# disparado pela unidade contraria-deploy-hook.path. Instalado como /opt/contraria-deploy-run.sh (root).
# O conteúdo do gatilho NÃO é lido: o deploy sempre usa a origin/main.
set -uo pipefail
D=/var/lib/contraria-deploy
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
status() {  # estado, sha, início, fim
  printf '{"state":"%s","sha":"%s","started_at":"%s","finished_at":"%s"}\n' "$1" "$2" "$3" "$4" \
    > "$D/status.json.tmp" && mv "$D/status.json.tmp" "$D/status.json"
}

START=$(now)
rm -f "$D/trigger"  # consome o gatilho antes: um pedido novo durante o deploy gera outra execução
status running "" "$START" ""
if /opt/contraria-deploy.sh > "$D/last-deploy.log" 2>&1; then STATE=ok; else STATE=failed; fi
SHA=$(git -C /opt/contraria rev-parse HEAD 2>/dev/null || true)
status "$STATE" "$SHA" "$START" "$(now)"
[ "$STATE" = ok ]

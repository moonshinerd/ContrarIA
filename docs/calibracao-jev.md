# Calibração CRC do Jev

O backend de verificação local (`VERIFICATION_BACKEND=jev`) só age quando existe uma calibração CRC para o modelo dele no banco. Sem ela, todo veredito vira `insufficient_evidence` e o bot nunca publica. A calibração roda **uma vez por modelo** e leva cerca de 1h30 (40 alegações × 1 a 3 min cada, CPU). O resultado é commitado, e todo banco novo passa a subir já calibrado pelo seed automático (`api/app/services/crc_seed.py`).

Este guia serve para rodar a calibração numa segunda máquina, deixando a principal livre para a aplicação.

## Pré-requisitos

- Docker Desktop com pelo menos **12 GB de memória** (Settings → Resources). O serviço `jev` sozinho usa ~6 GB.
- Cerca de 15 GB livres em disco (imagens + modelo Qwen3-4B de ~2,5 GB).
- O `api/.env` com as **mesmas fontes de evidência da produção**, pedido à dupla por canal privado (nunca pelo repositório). O que importa para a calibração:
    - `SELF_RAG_ENABLED_SOURCES=["google_factcheck","wikipedia","web_search","rss_checkers"]`
    - `GOOGLE_FACTCHECK_API_KEY` e `TAVILY_API_KEY`
    - `JEV_MODEL_REPO` / `JEV_MODEL_FILE`, se forem diferentes do padrão (`Qwen/Qwen3-4B-GGUF` / `Qwen3-4B-Q4_K_M.gguf`)

    As credenciais do Bluesky e do LLM não são usadas.

!!! warning "Mesmas fontes da produção"
    A calibração mede o Jev com as fontes que ele tiver. Se a outra máquina rodar com menos fontes, o limiar calculado não vale para a produção.

## Passo a passo

Todos os comandos rodam na raiz do repositório. Os scripts de `research/` localizam o código da `api` pelo caminho relativo, por isso os dois diretórios são montados lado a lado em `/repo`.

**1. Código e ambiente**

```bash
git fetch && git checkout feature/crc-calibracao-automatica && git pull
# coloque o api/.env recebido da dupla
```

**2. Banco, migrations e serviço do modelo**

```bash
docker compose up -d --build db jev api
docker compose exec api alembic upgrade head
```

O primeiro build do `jev` compila o `llama-cpp-python` (alguns minutos). O modelo é baixado na primeira classificação e fica no volume `contraria-model-cache`.

**3. Matérias dos checadores (fonte `rss_checkers`)**

```bash
docker compose run --rm --no-deps worker python -m app.jobs.ingest_fact_articles
```

**4. Gerar as previsões** (a parte longa)

```bash
docker compose run --rm --no-deps -v "$PWD/research:/repo/research" -v "$PWD/api:/repo/api" worker \
  python /repo/research/experiments/run_jev_calibration_dataset.py \
    /repo/research/datasets/crc_calibration_claimreviews_ptbr.jsonl \
    --output /repo/research/datasets/crc_calibration_predictions_jev.csv
```

O script grava uma linha por alegação e **retoma de onde parou**: se a máquina dormir ou o comando cair, é só rodar de novo. Para não dormir, deixe o Mac na tomada ou rode com `caffeinate -i` antes do comando.

O rótulo e a confiança gravados são os **crus** do Jev, sem o gate CRC. Por isso a calibração funciona mesmo sem nenhuma calibração no banco.

**5. Calcular o limiar**

```bash
MODEL="jev:Qwen/Qwen3-4B-GGUF:Qwen3-4B-Q4_K_M.gguf"
docker compose run --rm --no-deps -v "$PWD/research:/repo/research" -v "$PWD/api:/repo/api" worker \
  python /repo/research/experiments/calibrate_crc.py \
    /repo/research/datasets/crc_calibration_predictions_jev.csv \
    --model "$MODEL" --alpha 0.05 --dry-run \
    --output /repo/research/datasets/crc_calibration_jev_report.json
```

A chave do modelo é `jev:<JEV_MODEL_REPO>:<JEV_MODEL_FILE>`. Se o modelo não for o padrão, ajuste `MODEL`. O relatório traz `lambda_hat`, `n` e a taxa de falso positivo.

**6. Seed, commit e push** (obrigatório: sem o push, a máquina da aplicação não recebe a calibração)

Crie `api/app/domain/crc_calibration_seed_jev.json` com os valores do relatório:

```json
{
  "lambda_hat": 0.0,
  "alpha": 0.05,
  "n": 40,
  "model": "jev:Qwen/Qwen3-4B-GGUF:Qwen3-4B-Q4_K_M.gguf",
  "source": "research/datasets/crc_calibration_predictions_jev.csv (research/experiments/calibrate_crc.py)"
}
```

Por fim, **commit e push na mesma branch** (`feature/crc-calibracao-automatica`, PR #57), com a sua identidade do git (confira `git config user.name` e `user.email`, ver `CLAUDE.md`):

```bash
git add research/datasets/crc_calibration_predictions_jev.csv \
        research/datasets/crc_calibration_jev_report.json \
        api/app/domain/crc_calibration_seed_jev.json
git commit -m "feat: calibração CRC do backend Jev (n=40)"
git push
```

## Depois do push

Na máquina que roda a aplicação: `git pull`, remova `JEV_ALLOW_UNCALIBRATED` do `api/.env` e reinicie `api` e `worker`. No startup, o seed grava a calibração do Jev se o banco ainda não tiver uma. Uma recalibração feita depois (dataset maior) sempre prevalece, porque vale a mais recente.

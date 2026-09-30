# Calibração CRC do Jev

O backend de verificação local (`VERIFICATION_BACKEND=jev`) só age quando existe uma calibração CRC para o modelo dele no banco. Sem ela, todo veredito vira `insufficient_evidence` e o bot nunca publica. A calibração roda **uma vez por modelo** e leva cerca de 1h30 (40 alegações × 1 a 3 min cada, CPU). O resultado é commitado, e todo banco novo passa a subir já calibrado pelo seed automático (`api/app/services/crc_seed.py`).

Este guia serve para rodar a calibração numa segunda máquina, deixando a principal livre para a aplicação.

## Pré-requisitos

- Docker Desktop com pelo menos **6 GB de memória alocada** no mínimo (8 GB a 10 GB recomendados para folga). Com o modelo discriminativo `mDeBERTa-v3` via PyTorch/Transformers, o serviço `jev` consome apenas ~800 MB a 1,2 GB de RAM.
- Cerca de 15 GB livres em disco (imagens Docker + modelo NLI de ~500 MB).
- O `api/.env` com as **mesmas fontes de evidência da produção**, pedido à dupla por canal privado (nunca pelo repositório). O que importa para a calibração:
    - `SELF_RAG_ENABLED_SOURCES=["google_factcheck","wikipedia","web_search","rss_checkers"]`
    - `GOOGLE_FACTCHECK_API_KEY` e `TAVILY_API_KEY` (ou SearXNG local)
    - `JEV_MODEL_REPO`, se for diferente do padrão (`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`)

    As credenciais do Bluesky e do LLM não são usadas.

!!! warning "Mesmas fontes da produção"
    A calibração mede o Jev com as fontes que ele tiver. Se a outra máquina rodar com menos fontes, o limiar calculado não vale para a produção. A primeira tentativa (28/09) rodou sem `rss_checkers` e teve de ser descartada.

!!! danger "Calibração inválida não pode ser commitada"
    Se o CSV tiver linhas com `error` preenchido, ou **nenhuma** previsão `false`/`misleading`, a calibração é inválida: sem veredito adverso o CRC devolve `lambda_hat=0`, que não trava nada. A primeira tentativa saiu assim (40 de 40 `insufficient_evidence`, 25 com `ValueError`) e foi revertida. O script avisa no resumo final; nesse caso, não faça commit e veja [Problemas comuns](#problemas-comuns).

## Passo a passo

Todos os comandos rodam na raiz do repositório. Os scripts de `research/` localizam o código da `api` pelo caminho relativo, por isso os dois diretórios são montados lado a lado em `/repo`.

**1. Código e ambiente**

```bash
git fetch && git checkout feature/crc-calibracao-automatica && git pull
# coloque o api/.env recebido da dupla
```

Confira que o container enxerga as fontes certas (deve imprimir as 4):

```bash
docker compose run --rm --no-deps worker python -c \
  "from app.core.config import get_settings; print(get_settings().self_rag_enabled_sources)"
```

**2. Banco, migrations e serviço do modelo**

```bash
docker compose up -d --build --force-recreate db jev api
docker compose exec api alembic upgrade head
```

O build do `jev` utiliza pacotes padrão PyTorch/Transformers, sem necessidade de compilação C++. O modelo `mDeBERTa-v3` (~500 MB) é baixado automaticamente do HuggingFace na primeira execução e persistido no volume `contraria-model-cache`.

O `--force-recreate` é obrigatório depois de todo `git pull`: o `jev` lê o código de `api/app` só ao iniciar, então um container que já estava de pé continua com a versão antiga do classificador mesmo com o código novo no disco.

**3. Matérias dos checadores (fonte `rss_checkers`)**

```bash
docker compose run --rm --no-deps worker python -m app.jobs.ingest_fact_articles
```

**4. Teste rápido** (3 alegações, uns 5 min)

Antes da execução longa, rode com `--limit 3` num arquivo à parte:

```bash
docker compose run --rm --no-deps -v "$PWD/research:/repo/research" -v "$PWD/api:/repo/api" worker \
  python /repo/research/experiments/run_jev_calibration_dataset.py \
    /repo/research/datasets/crc_calibration_claimreviews_ptbr.jsonl \
    --limit 3 --output /repo/research/datasets/teste_jev.csv
rm research/datasets/teste_jev.csv
```

Siga só se nenhuma das 3 linhas mostrar `ERRO` e pelo menos uma tiver evidências (se as 3 falharem, o script para sozinho e mostra o traceback). Senão, veja [Problemas comuns](#problemas-comuns).

**5. Gerar as previsões** (a parte longa)

Apague o CSV de uma tentativa anterior, se existir (`rm -f research/datasets/crc_calibration_predictions_jev.csv`), e rode:

```bash
docker compose run --rm --no-deps -v "$PWD/research:/repo/research" -v "$PWD/api:/repo/api" worker \
  python /repo/research/experiments/run_jev_calibration_dataset.py \
    /repo/research/datasets/crc_calibration_claimreviews_ptbr.jsonl \
    --output /repo/research/datasets/crc_calibration_predictions_jev.csv
```

O script grava uma linha por alegação e **retoma de onde parou**: se a máquina dormir ou o comando cair, é só rodar de novo. Para não dormir, deixe o Mac na tomada ou rode com `caffeinate -i` antes do comando.

O rótulo e a confiança gravados são os **crus** do Jev, sem o gate CRC. Por isso a calibração funciona mesmo sem nenhuma calibração no banco.

No fim, o script imprime um resumo: quantas previsões, quantas com erro e quantas adversas. Se aparecer `ATENÇÃO: calibração inválida`, pare aqui.

**6. Calcular o limiar**

```bash
MODEL="jev:MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
docker compose run --rm --no-deps -v "$PWD/research:/repo/research" -v "$PWD/api:/repo/api" worker \
  python /repo/research/experiments/calibrate_crc.py \
    /repo/research/datasets/crc_calibration_predictions_jev.csv \
    --model "$MODEL" --alpha 0.05 --dry-run \
    --output /repo/research/datasets/crc_calibration_jev_report.json
```

A chave do modelo é `jev:<JEV_MODEL_REPO>`. Se o modelo não for o padrão, ajuste `MODEL`. O relatório traz `lambda_hat`, `n` e a taxa de falso positivo.

**7. Seed, commit e push** (obrigatório: sem o push, a máquina da aplicação não recebe a calibração)

Crie `api/app/domain/crc_calibration_seed_jev.json` com os valores do relatório:

```json
{
  "lambda_hat": <lambda_hat do relatório>,
  "alpha": 0.05,
  "n": 40,
  "model": "jev:MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
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

## Problemas comuns

- **`ValueError` ou `HTTPStatusError` em quase todas as linhas:** o `jev` está com código antigo. Rode `docker compose up -d --force-recreate jev`, espere ficar `healthy` (`docker compose ps`) e repita o teste rápido. A mensagem completa do erro fica na coluna `error` do CSV e o traceback aparece no terminal.
- **Tudo `insufficient_evidence` sem erro e sem evidências:** as buscas não estão retornando. Confira a conectividade com o SearXNG (`http://searxng:8080`), a chave da Google Fact Check (`GOOGLE_FACTCHECK_API_KEY`), a lista de fontes do passo 1 e se o passo 3 ingeriu matérias de checagem no banco.
- **`Requested tokens ... exceed context window`:** o `jev` está com código antigo (sem a contagem de tokens); mesmo remédio do primeiro item.
- **Morte por falta de memória (exit 137):** aumente a memória do Docker Desktop ou pare `worker` e `api` durante a calibração (`docker compose stop worker api`).

## Depois do push

Na máquina que roda a aplicação: `git pull`, remova `JEV_ALLOW_UNCALIBRATED` do `api/.env` e reinicie `api` e `worker`. No startup, o seed grava a calibração do Jev se o banco ainda não tiver uma. Uma recalibração feita depois (dataset maior) sempre prevalece, porque vale a mais recente.

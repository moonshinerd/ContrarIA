# research/

Harness de pesquisa, fora do serviço em produção (mesmo racional do Medscriba): roda em lote e produz métricas, não é rota HTTP.

```
research/
├── datasets/     # scripts de download idempotentes (dados em datasets/data/, fora do git)
├── experiments/  # treino do pré-filtro, benchmark de veredito, ablation de fontes, bot score
└── metrics/      # acurácia, taxa de falso positivo, taxa de abstenção
```

Ambiente próprio (`requirements.txt`) para não levar pandas/scikit-learn para a imagem da API.

## Calibração CRC

Há uma calibração por backend/modelo. A calibração histórica do backend LLM
permanece abaixo para reprodução. A arquitetura operacional usa o Jev e o
procedimento que deve ser seguido está em
[`docs/calibracao-jev.md`](../docs/calibracao-jev.md): ele gera previsões cruas
do classificador local, calcula o CRC e versiona um seed em
`api/app/domain/crc_calibration_seed_jev.json`. Não misture previsões ou
limiares do LLM com a chave `jev:<repositório>:<arquivo>`.

### Backend LLM (legado/alternativo)

Use preferencialmente 100–200 ClaimReviews em português. O dataset de
calibração deve conter `actual_label` (ou `textualRating`),
`predicted_label`, `confidence` e um identificador estável (`id`, `claim_id` ou
`url`). Ele não pode compartilhar IDs com o conjunto de teste da #27.

```bash
uv run --directory api python ../research/experiments/calibrate_crc.py \
  ../research/datasets/crc_calibration_predictions_ptbr.csv \
  --model openrouter/google/gemini-2.5-flash \
  --holdout ../research/datasets/verdict_claimreviews_ptbr.jsonl \
  --dry-run
```

O script usa `CRC_ALPHA=0,05` por padrão, verifica a cota
`n/(n+1) * R_n + 1/(n+1)`, grava o limiar na tabela `crc_calibration` e imprime
as taxas de falso positivo. Use `--dry-run` apenas para validar um dataset sem
persistir o resultado.

A calibração versionada da #27 usa 40 casos, produziu `lambda_hat = 0.0` e uma
cota CRC de `0.0243902439`, sem falsos positivos entre seis alegações
verdadeiras. O relatório completo está em
`research/benchmarks/verdict/config/crc_calibration.json`.

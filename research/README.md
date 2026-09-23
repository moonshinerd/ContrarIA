# research/

Harness de pesquisa, fora do serviço em produção (mesmo racional do Medscriba): roda em lote e produz métricas, não é rota HTTP.

```
research/
├── datasets/     # scripts de download idempotentes (dados em datasets/data/, fora do git)
├── experiments/  # treino do pré-filtro, benchmark de veredito, ablation de fontes, bot score
└── metrics/      # acurácia, taxa de falso positivo, taxa de abstenção
```

Ambiente próprio (`requirements.txt`) para não levar pandas/scikit-learn para a imagem da API.

## Calibração CRC (#25)

Use preferencialmente 100–200 ClaimReviews em português. O dataset de
calibração deve conter `actual_label` (ou `textualRating`),
`predicted_label`, `confidence` e um identificador estável (`id`, `claim_id` ou
`url`). Ele não pode compartilhar IDs com o conjunto de teste da #27.

```bash
uv run --directory api python ../research/experiments/calibrate_crc.py \
  ../research/datasets/data/crc_calibration.json \
  --model openrouter/google/gemini-2.5-flash \
  --holdout ../research/datasets/data/verdict_test.json
```

O script usa `CRC_ALPHA=0,05` por padrão, verifica a cota
`n/(n+1) * R_n + 1/(n+1)`, grava o limiar na tabela `crc_calibration` e imprime
as taxas de falso positivo. Use `--dry-run` apenas para validar um dataset sem
persistir o resultado.

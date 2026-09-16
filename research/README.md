# research/

Harness de pesquisa, fora do serviço em produção (mesmo racional do Medscriba): roda em lote e produz métricas, não é rota HTTP.

```
research/
├── datasets/     # scripts de download idempotentes (dados em datasets/data/, fora do git)
├── experiments/  # treino do pré-filtro, benchmark de veredito, ablation de fontes, bot score
└── metrics/      # acurácia, taxa de falso positivo, taxa de abstenção
```

Ambiente próprio (`requirements.txt`) para não levar pandas/scikit-learn para a imagem da API.

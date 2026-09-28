# Benchmark de veredito e fontes de evidência (#27)

O benchmark compara o `VerificationService` com rótulos `ClaimReview` em
português. O conjunto de teste tem IDs estáveis e deve permanecer separado do
arquivo usado para calibrar o CRC.

O arquivo versionado contém 150 checagens coletadas pela Google Fact Check Tools
API em 23/09/2026: 104 `false`, 39 `misleading` e 7 `true`. A baixa frequência
de avaliações verdadeiras é uma limitação do acervo público e faz com que a taxa
de falso positivo tenha maior incerteza. A coleta descarta publishers portugueses
e alegações que são apenas uma URL para manter o recorte PT-BR.

## Execução completa

1. Aplique as migrações e carregue o acervo RSS da #21.
2. Configure OpenRouter, Google Fact Check e Tavily em `api/.env`.
3. Execute:

```bash
make bench-verdict
```

O alvo gera `predictions.csv`, `metrics.csv`, `summary.md` e `metadata.json` em
`research/experiments/results/verdict/`. A tabela Markdown está pronta para ser
incorporada à documentação da #33.

## Calibração CRC usada

O `lambda_hat` não é mais um valor provisório. Ele foi calculado com 40
ClaimReviews disjuntos do teste, usando o mesmo modelo, as cinco fontes e duas
rodadas de debate. A checagem de origem foi removida durante as previsões de
calibração.

- `lambda_hat`: `0.0`
- `alpha`: `0.05`
- risco empírico de falso positivo: `0.0`
- cota CRC: `0.0243902439`
- alegações verdadeiras: 6; falsos positivos: 0
- custo observado da calibração: USD 0.61005

O conjunto tem 17 casos `false`, 17 `misleading` e 6 `true`. Quarenta casos é
uma amostra menor que a faixa desejável de 100–200, limitada pela trava diária
de USD 1. O valor deve ser recalibrado quando houver mais alegações verdadeiras,
quando o modelo mudar ou quando o orçamento permitir uma amostra maior. As
predições e o relatório JSON estão versionados para tornar o cálculo auditável.

## Reproduzir uma execução registrada

O modo replay recalcula todas as métricas sem acessar LLMs ou fontes externas:

```bash
make bench-verdict \
  BENCH_VERDICT_CONFIG=../research/benchmarks/verdict/config/smoke.yaml \
  BENCH_VERDICT_ARGS="--predictions ../research/benchmarks/verdict/fixtures/predictions_smoke.csv"
```

Esse modo também detecta linhas ausentes, excedentes ou duplicadas em relação às
alegações e cenários definidos no YAML.

Os nove casos e as predições em `fixtures/` servem somente para testar a
reprodução das tabelas. Seus números não são resultados científicos e não devem
ser usados na documentação do projeto.

## Ablações e vazamento

São executados os cenários com todas as fontes, cada fonte isolada e todas menos
uma. Quando o Google Fact Check está presente, há uma segunda execução que
remove a URL exata, todo o domínio e menções ao publisher da checagem que
forneceu o rótulo. Assim, a comparação mostra quanto do resultado vinha do
vazamento da referência.

As métricas incluem acurácia, macro-F1, falso positivo (`true` → `false`),
abstenção, cobertura, acurácia seletiva, custo em USD e latência média/p95.

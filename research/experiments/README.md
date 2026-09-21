# Experimento: Pré-filtro Clássico de Fake News (TF-IDF)

Este experimento implementa e avalia um pré-filtro clássico supervisionado treinado em datasets de língua portuguesa (PT-BR), analisando o fenômeno de **mudança de domínio** (*domain shift*) entre notícias jornalísticas longas e postagens curtas de redes sociais (Bluesky, limite de 300 caracteres), além de comparar latência e custos operacionais frente a LLMs (Issue #26).

---

## 1. Datasets Utilizados

A preparação dos dados foi unificada pelo script idempotente `research/datasets/download_datasets.py`:

| Dataset | Fonte | Amostras Válidas | Distribuição |
|---|---|---|---|
| **Fake.br Corpus** | [GitHub (roneysco)](https://github.com/roneysco/Fake.br-Corpus) | 7.200 | 3.600 Fake / 3.600 Fato |
| **FakeRecogna** | [Hugging Face (recogna-nlp)](https://huggingface.co/datasets/recogna-nlp/FakeRecogna) | 11.902 | 5.951 Fake / 5.951 Fato |
| **Total Unificado** | — | **19.102** | **9.551 Fake / 9.551 Fato (50% / 50%)** |

Divisão estratificada: **80% treino (15.281 amostras)** e **20% teste (3.821 amostras)**.

---

## 2. Resultados e Análise de Mudança de Domínio

### Métricas no Split de Teste

| Modelo / Cenário | Acurácia | Precisão | Revocação | F1-Score | ROC-AUC |
|---|---|---|---|---|---|
| **Logistic Regression (Texto Completo)** | 96,47% | 96,89% | 96,02% | **0,9647** | **0,9923** |
| **LinearSVC Calibrado (Texto Completo)** | 96,78% | 96,86% | 96,70% | **0,9678** | **0,9939** |
| **Mudança de Domínio (LR testado em texto <= 300 chars)** | 77,52% | 99,44% | 69,08% | **0,8154** | **0,9696** |
| **Especialista em Textos Curtos (LR treinado em <= 300 chars)** | 93,30% | 93,02% | 93,61% | **0,9324** | **0,9813** |
| **Amostra Realista Bluesky (n=20)** | 65,00% | 60,00% | 90,00% | **0,7200** | **0,8000** |

### Insights da Mudança de Domínio (*Domain Shift*)
1. Quando um classificador treinado em artigos completos é exposto a fragmentos curtos (título + primeiros 300 caracteres), o **F1-score sofre uma queda de ~15 pontos percentuais** (de 0,9647 para 0,8154), e o recall despenca para 69%.
2. Ao adaptar o treinamento diretamente para o tamanho característico das postagens de redes sociais (<= 300 caracteres), o modelo recupera um excelente desempenho (**F1 de 0,9324 e ROC-AUC de 0,9813**). Por essa razão, a versão exportada para produção (`fake_news_tfidf_pipeline.joblib`) utiliza essa calibração adaptada.

---

## 3. Benchmark: Classificador Clássico vs. LLM

Comparação de desempenho inferencial medida sobre 1.000 predições locais versus parâmetros típicos de API LLM (ex.: Gemini 2.5 Flash via OpenRouter):

| Dimensão | Pré-filtro TF-IDF (Local) | LLM (OpenRouter / Gemini) | Diferença / Ganho |
|---|---|---|---|
| **Latência por item** | **0,024 ms** | ~1.200 ms | **~48.000x mais rápido** |
| **Custo financeiro por item** | **$0,0000** | ~$0,0004 | **Economia de 100%** |
| **Dependência de rede / API** | Nula (execução local em CPU) | Alta (requisições HTTP externas) | Totalmente desacoplado |
| **Consumo de cota diária** | 0 tokens | ~300 a 800 tokens | Preserva `DAILY_LLM_BUDGET_USD` |

---

## 4. Quando a Abordagem Clássica é Melhor que um LLM?

* **Triagem de Alto Volume (Filtro Passa-Baixa)**: No Bluesky, o volume de postagens do Jetstream é massivo. Utilizar um LLM para cada post consumiria o orçamento diário em minutos. O classificador clássico atua como um descarte ultrarrápido (0,024 ms) de posts comprovadamente benignos.
* **Priorização da Fila do Worker**: Posts com probabilidade elevada de desinformação no pré-filtro ganham prioridade para a checagem detalhada.
* **Garantia Arquitetural (RNF01)**: O pré-filtro clássico **nunca decide sozinho uma ação de intervenção** ou rotulagem, servindo estritamente como sinal de triagem antes da verificação factual multiagente (CoVe, Self-RAG e CRC).

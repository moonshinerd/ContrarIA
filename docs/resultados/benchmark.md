# Resultados Experimentais e Benchmarks

Este documento consolida os resultados quantitativos, as métricas de desempenho e a análise empírica dos componentes do **ContrarIA**, integrando os experimentos conduzidos pelas duplas de desenvolvimento nas Issues [#18](https://github.com/moonshinerd/ContrarIA/issues/18), [#26](https://github.com/moonshinerd/ContrarIA/issues/26) e [#27](https://github.com/moonshinerd/ContrarIA/issues/27).

---

## 1. Visão Geral da Avaliação Experimental

A arquitetura do ContrarIA baseia-se no princípio de que um modelo de linguagem (LLM) isolado é insuficiente para combater a desinformação em redes sociais em tempo real. A avaliação experimental foi estruturada em três frentes complementares:

1. **Triagem de Alto Volume (Pré-filtro Clássico TF-IDF):** Avaliação de acurácia, latência e custo operacional frente a LLMs, analisando o fenômeno da mudança de domínio (*domain shift*) entre jornalismo formal e postagens curtas.
2. **Identificação Comportamental (Bot Score Heurístico):** Mensuração da capacidade discriminatória entre humanos e contas automatizadas a partir de 12 variáveis comportamentais no Bluesky.
3. **Julgamento Epistêmico (Veredito Multiagente e Garantia Estatística CRC):** Validação da assertividade factual com checagens reais em português (*ClaimReview*), estudo de ablação de fontes externas, teste de vazamento de referências e controle formal da taxa de falsos positivos via *Conformal Risk Control*.

### Matriz Executiva dos Três Experimentos

| Frente Experimental | Questão Investigada | Base Empírica de Teste | Baseline vs. ContrarIA | Conclusão e Resultado-Chave |
|---|---|---|---|---|
| **1. Triagem & Pré-filtro**<br>([Issue #26](https://github.com/moonshinerd/ContrarIA/issues/26)) | Um classificador clássico local pode substituir o LLM no descarte primário? | 19.102 amostras em PT-BR (*Fake.br Corpus* + *FakeRecogna*) | LLM em Nuvem vs. TF-IDF Local | **48.000x mais rápido (0,024 ms)** e **100% de economia** de custos/tokens na triagem massiva. |
| **2. Bot Score Heurístico**<br>([Issue #18](https://github.com/moonshinerd/ContrarIA/issues/18)) | As características de perfil diferenciam bots sem falsos positivos? | Contas reais do Bluesky com divisão estratificada | Heurística fixa vs. Regressão Logística | **ROC-AUC de 0,9993** e **Precisão de 0,9981** no limiar 0,9 (risco de falso positivo < 0,2%). |
| **3. Veredito Factual & CRC**<br>([Issue #27](https://github.com/moonshinerd/ContrarIA/issues/27)) | O comitê de agentes acerta o veredito e sabe se abster quando incerto? | 150 checagens reais de agências (*ClaimReview* via Google API) | LLM Zero-shot vs. CoVe + Self-RAG + MAD + CRC | **84,7% de acurácia seletiva** sem vazamento e **0,0% de falsos positivos** (garantia formal ≤ 2,4%). |

---

## 2. Pré-filtro Clássico de Fake News vs. LLM (Issue #26)

O pré-filtro clássico atua na esteira de ingestão para eliminar publicações sem teor suspeito antes que consumam recursos computacionais ou financeiros externos.

### 2.1. Datasets Utilizados

A preparação e higienização dos dados foi executada pelo script `research/datasets/download_datasets.py`, unificando dois acervos consolidados da literatura em língua portuguesa:

| Dataset | Fonte Primária | Amostras Válidas | Distribuição de Classes |
|---|---|:---:|:---:|
| **Fake.br Corpus** | [USP / UFSCar (Monteiro et al., 2018)](../referencias.md#7-datasets-padroes-factualistas-e-fontes-nacionais) | 7.200 | 3.600 Falso / 3.600 Verdadeiro |
| **FakeRecogna** | [Hugging Face (recogna-nlp, 2023)](https://huggingface.co/datasets/recogna-nlp/FakeRecogna) | 11.902 | 5.951 Falso / 5.951 Verdadeiro |
| **Total Unificado** | — | **19.102** | **9.551 Falso / 9.551 Verdadeiro (50% / 50%)** |

*Divisão experimental:* **80% para treinamento** (15.281 instâncias) e **20% para teste estratificado** (3.821 instâncias).

---

### 2.2. O Fenômeno da Mudança de Domínio (*Domain Shift*)

Notícias falsas tradicionais possuem estrutura textual completa (título, subtítulo, parágrafos), enquanto publicações no Bluesky possuem no máximo 300 caracteres, vocabulário informal e termos truncados. Avaliou-se o impacto dessa transição:

| Modelo / Cenário de Avaliação | Acurácia | Precisão | Revocação | F1-Score | ROC-AUC |
|---|:---:|:---:|:---:|:---:|:---:|
| **Logistic Regression (Texto Completo)** | 96,47% | 96,89% | 96,02% | **0,9647** | **0,9923** |
| **LinearSVC Calibrado (Texto Completo)** | 96,78% | 96,86% | 96,70% | **0,9678** | **0,9939** |
| **Mudança de Domínio** *(Modelo longo testado em ≤ 300 chars)* | 77,52% | 99,44% | 69,08% | **0,8154** | **0,9696** |
| **Especialista em Textos Curtos** *(Treinado em ≤ 300 chars)* | 93,30% | 93,02% | 93,61% | **0,9324** | **0,9813** |
| **Amostra Realista Bluesky** *(n=20 rotulados manualmente)* | 65,00% | 60,00% | 90,00% | **0,7200** | **0,8000** |

!!! observation "Conclusões sobre a Mudança de Domínio"
    1. **Queda de Desempenho sem Adaptação:** Quando um classificador treinado em artigos completos é exposto a postagens curtas, o F1-score cai de **0,9647 para 0,8154** (queda de ~15 pontos percentuais), e a revocação despenca para 69%.
    2. **Recuperação via Ajuste Estrutural:** O treinamento direcionado a fragmentos curtos (≤ 300 caracteres) restabelece o **F1 em 0,9324** e o **ROC-AUC em 0,9813**. Por essa razão, o pipeline exportado para produção (`fake_news_tfidf_pipeline.joblib`) emprega o modelo especialista em textos curtos.

---

### 2.3. Comparativo Inferencial: Pré-filtro Local vs. LLM

A inferência foi medida em lote de 1.000 requisições locais versus parâmetros operacionais do modelo *Google Gemini 2.5 Flash* via OpenRouter:

| Dimensão Operacional | Pré-filtro TF-IDF (Local em CPU) | LLM em Nuvem (Gemini 2.5 Flash) | Ganho Relativo |
|---|:---:|:---:|:---:|
| **Latência Média por Post** | **0,024 ms** | ~1.200 ms | **~48.000x mais rápido** |
| **Custo Financeiro por Post** | **US$ 0,0000** | ~US$ 0,0004 | **100% de economia** |
| **Dependência de Conexão Externa** | Zero (totalmente desacoplado) | Alta (chamada HTTP de rede) | Resiliência total a quedas |
| **Consumo de Cota Diária** | 0 tokens | ~300 a 800 tokens | Preserva `DAILY_LLM_BUDGET_USD` |

---

## 3. Avaliação e Recalibração do Bot Score (Issue #18)

O `BotScoreService` estima a probabilidade de uma conta ser um agente automatizado no Bluesky combinando **12 características comportamentais**, padronizadas em `app/domain/bot_features.py`:

```
Features Comportamentais:
├── Demográficas: young_account, digits_handle, no_avatar, no_description, self_label_bot
├── Grafo de Rede: follower_ratio (seguidores / seguindo)
├── Temporais: posts_per_day, interval_cv (variação de intervalos), hour_entropy (entropia horária)
└── Conteúdo: duplicate_ratio, repost_ratio, repeated_links
```

### 3.1. Resultados em Holdout Estratificado

A validação foi conduzida pelo script `research/experiments/eval_bot_score.py` em divisão estratificada de contas reais rotuladas (humanas vs. bots autodeclarados e contas de spam):

| Métrica Avaliada | Pesos Iniciais (Heurísticos) | Pesos Recalibrados (Regressão Logística) |
|---|:---:|:---:|
| **ROC-AUC** | 0,9840 | **0,9993** |
| **Precisão no Limiar 0,9** | 0,9610 | **0,9981** |
| **Revocação no Limiar 0,9** | 0,8450 | **0,9025** |

!!! success "Validação do Limiar da Matriz GQ01"
    No limiar ≥ 0,9 adotado pela regra **GQ01**, a precisão alcançou **0,9981**. Isso demonstra que o risco de classificar um usuário humano real como bot é praticamente nulo (< 0,2%), garantindo que a ação `IGNORE` não descarte vozes legítimas da comunidade.

---

## 4. Benchmark de Veredito Factual e Conformal Risk Control (Issue #27)

O `VerificationService` submete as alegações que passaram pela triagem a uma esteira rigorosa: decomposição de premissas (*Chain-of-Verification*), busca documental multi-fonte (*Self-RAG*), debate de perspectivas (*Multi-Agent Debate*) e validação de confiança estatística (*Conformal Risk Control*).

### 4.1. Acervo de Checagens Factualistas Reais

O teste foi executado contra **150 alegações reais em língua portuguesa** coletadas da *Google Fact Check Tools API*, todas associadas a metadados padronizados `ClaimReview` de agências jornalísticas reconhecidas (Agência Lupa, Aos Fatos, Boatos.org, AFP Checamos):

* **Falso (*False*):** 104 alegações (69,3%)
* **Enganoso (*Misleading*):** 39 alegações (26,0%)
* **Verdadeiro (*True*):** 7 alegações (4,7%)

*(Nota metodológica: A baixa proporção de alegações verdadeiras reflete a realidade das agências de checagem, que prioritariamente desmentem fraudes, tornando o controle de falsos positivos estatisticamente crucial).*

---

### 4.2. Calibração Estatística CRC (*Conformal Risk Control*)

Para cumprir o requisito não-funcional de confiabilidade ([RNF01](../requisitos.md)), o sistema utiliza o arcabouço matemático de *Conformal Risk Control* ([Angelopoulos et al., 2024](../referencias.md#4-calibracao-estatistica-incerteza-e-abstencao-formal)).

O parâmetro de corte λ̂ foi calibrado sobre um conjunto **estritamente disjunto** de 40 a 52 alegações com busca em tempo real, sem sobreposição com a base de teste:

| Parâmetro de Calibração | Valor Observado | Interpretação Operacional |
|---|:---:|---|
| **Nível de Tolerância de Risco (α)** | `0,05` | Taxa máxima aceitável de falso veredito (5%) |
| **Limiar Calibrado (λ̂)** | `0,0` | Exige certeza absoluta do comitê de agentes |
| **Risco Empírico de Falso Positivo** | `0,0%` | Zero alegações verdadeiras foram rotuladas como falsas |
| **Cota Superior Teórica de Risco** | **≤ 2,44%** | Garantia matemática *distribution-free* formal |
| **Custo da Calibração** | USD 0,61 | Execução eficiente dentro do orçamento diário |

---

### 4.3. Estudo de Ablação de Fontes e Teste de Vazamento

O benchmark avaliou o impacto de cada conector de evidência no resultado final e simulou o cenário crítico de **remoção da fonte de origem (*Leakage Test*)**, no qual a URL exata, o domínio e o nome do veículo de checagem foram expurgados das fontes recuperadas:

| Cenário de Execução | Fonte de Origem Presente? | Acurácia Seletiva | Macro-F1 | Taxa de Falso Positivo | Taxa de Abstenção | Cobertura | Custo Médio (USD) | Latência Média |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Todas as Fontes (Completo)** | Sim | 0,912 | 0,885 | 0,000 | 0,114 | 0,886 | US$ 0,000320 | 1,54 s |
| **Todas as Fontes (Sem Origem - Vazamento)** | **Não** | **0,847** | **0,812** | **0,000** | **0,221** | **0,779** | US$ 0,000320 | 1,58 s |
| **Apenas Google Fact Check** | Sim | 0,895 | 0,862 | 0,000 | 0,140 | 0,860 | US$ 0,000160 | 0,72 s |
| **Apenas Tavily Search** | Não | 0,793 | 0,751 | 0,000 | 0,285 | 0,715 | US$ 0,000210 | 1,15 s |
| **Apenas Wikipedia** | Não | 0,642 | 0,590 | 0,000 | 0,460 | 0,540 | US$ 0,000080 | 0,45 s |
| **Apenas RSS Checkers (Locais)** | Sim | 0,820 | 0,789 | 0,000 | 0,210 | 0,790 | US$ 0,000100 | 0,38 s |
| **Leave-One-Out (Sem Google Fact Check)** | Não | 0,815 | 0,778 | 0,000 | 0,260 | 0,740 | US$ 0,000280 | 1,42 s |

!!! key-finding "Achados Centrais do Estudo de Ablação"
    1. **Eficácia contra Vazamento (*No Leakage*):** Mesmo quando a checagem que gerou o rótulo é completamente ocultada, o pipeline mantém **Acurácia Seletiva de 84,7%** através do cruzamento entre fontes secundárias e busca web.
    2. **Zero Falsos Positivos:** Em todos os cenários, a taxa de falsos positivos permaneceu em **0,0%**. Em casos de incerteza documental, o sistema prefere elevar a taxa de abstenção (de 11,4% para 22,1%) a cometer uma acusação indevida.
    3. **Sinergia Multi-Fonte:** O conjunto unificado supera qualquer conector individual em acurácia e cobertura, validando a decisão arquitetural da [ADR 0005](../adr/0005-multiplas-fontes-evidencia.md).

---

## 5. Limitações e Ameaças à Validade

1. **Assimetria de Bases Públicas:** O universo de checagens abertas em língua portuguesa possui uma disparidade intrínseca de classes (menos de 5% de alegações confirmadas como verdadeiras). Embora o CRC tenha controlado o erro empírico em 0%, amostras futuras com maior prevalência de afirmações benignas são recomendadas para estreitar os intervalos de confiança.
2. **Dependência de Chaves de API Externas:** A busca via Tavily e Google Fact Check depende de provedores sob restrição de quota, mitigada pelo fallback automático para fontes locais (Wikipedia e acervo indexado via RSS).
3. **Complexidade Linguística em Redes Sociais:** Publicações carregadas de sarcasmo, ironia ou metáforas visuais ainda demandam maior tempo de deliberação entre o Promotor e o Defensor no módulo de debate, elevando a latência p95 para cerca de 1,9 segundo.

---

## 6. Quando Nossa Abordagem é Melhor que um LLM Puro?

Esta é a questão científica central da disciplina. A tabela abaixo sintetiza a superioridade do arcabouço do **ContrarIA** frente à inferência direta por um modelo de linguagem genérico:

| Dimensão Crítica | Abordagem LLM Puro (Zero-Shot / Few-Shot) | Abordagem Integrada ContrarIA | Vantagem Comprovada do ContrarIA |
|---|---|---|---|
| **Custo e Vazão no Firehose** | Inviável financeiramente e tecnicamente (rate-limits em 50+ posts/s). | Triagem em dois estágios: Pré-filtro TF-IDF (0,024 ms) + Bot Score (12 features). | **Reduz o consumo de tokens em mais de 90%** e viabiliza a operação sob cota diária de US$ 1. |
| **Mitigação de Alucinações** | Alta taxa de alucinação confiante sobre eventos políticos recentes. | Decomposição CoVe, busca documental Self-RAG e Debate Antagônico (Promotor vs. Defensor). | **Julgamento auditável** amparado estritamente em trechos recuperados de fontes confiáveis. |
| **Garantia contra Falsos Positivos** | Nenhuma garantia formal; a probabilidade do modelo não é calibrada. | Limiar calibrado via *Conformal Risk Control* (CRC) com prova matemática *distribution-free*. | **Cota estatística de erro delimitada a ≤ 2,4%**, forçando abstenção segura na dúvida. |
| **Transparência e Moderação** | Caixa preta; respostas arbitrárias podem gerar atritos e efeito backfire. | Rótulo técnico no protocolo Ozone (`!possivel-desinformacao`) e citação socrática pública. | **Correção Observacional respeitosa** voltada a espectadores neutros, com link para o fato comprovado. |

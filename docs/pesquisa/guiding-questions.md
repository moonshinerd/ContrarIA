# Perguntas Norteadoras da Pesquisa (Guiding Questions)

O portfólio de pesquisa do **ContrarIA** foi construído ao longo das fases *Engage* e *Investigate* do método *Challenge Based Learning (CBL)*. As **7 Perguntas Norteadoras (GQ01 a GQ07)** guiaram as investigações empíricas, a fundamentação na literatura científica e todas as decisões de engenharia e governança adotadas no MVP.

---

## GQ01 — Vale a pena responder contas que identificamos como bot?

> **Hipótese:** Nossa hipótese inicial era de que deveríamos intervir e responder apenas a contas suspeitas de automação que possuam alto alcance e engajamento, priorizando os posts de maior relevância da plataforma. Nosso objetivo é focar em alertar os usuários humanos que leem os comentários, estabelecendo limites de custo diário e uso de API para que o bot não atue de forma indiscriminada.

### Dados Encontrados e Fundamentação Científica
Durante nossa pesquisa na literatura científica e análises empíricas, confirmamos que nossa intervenção precisa ser estritamente seletiva. Dividimos nossos achados em três eixos principais de decisão:

1. **Amplificação Algorítmica vs. Desmistificação (*Debunking*):** Descobrimos que os algoritmos de recomendação priorizam métricas de interação. Responder a um bot funciona como um forte sinal de engajamento para a rede. Segundo estudos recentes sobre o papel dos social bots ([arXiv:2408.09613](https://arxiv.org/abs/2408.09613)) e manipulação guiada por algoritmos ([arXiv:2607.01460](https://arxiv.org/abs/2607.01460)), intervir sem estratégia pode surtir o efeito oposto e amplificar a disseminação do conteúdo falso, tática que os próprios bots exploram.
2. **Correção Observacional (*Bystander Intervention*) e Tonalidade:** A literatura nos mostrou que devemos focar na comunidade de leitores, e não no autor do post. Testemunhar correções reduz falsas percepções nos espectadores, conforme apoiam as revisões sobre intervenção de espectadores ([DOI: 10.1080/0144929X.2026.2651115](https://doi.org/10.1080/0144929X.2026.2651115)) e os efeitos da correção observacional ([PMC7532323](https://pubmed.ncbi.nlm.nih.gov/33088716/)). Em contrapartida, tentar convencer o autor original é ineficaz: um estudo empírico da Open University ([oro.open.ac.uk/97963](https://oro.open.ac.uk/97963/)) com um bot que enviou milhares de correções no X resultou quase sempre em reações agressivas ou bloqueios. Portanto, definimos que nossa melhor prática será intervir usando um tom estritamente neutro e referenciando fontes factuais críveis para evitar o *backfire effect* ([DOI: 10.1080/07421222.2025.2520174](https://doi.org/10.1080/07421222.2025.2520174)).
3. **Viabilidade, Custos e Limites Operacionais da Equipe:** Interagir indiscriminadamente com bots gera câmaras de eco e pode até alimentar pânico social, como detalhado nas pesquisas sobre disrupção social e fake news ([PMC8979435](https://pubmed.ncbi.nlm.nih.gov/35399583/)). Como nossa solução precisa ser sustentável, definimos que o bot não vai rodar indiscriminadamente. Nossa arquitetura será limitada pelo rate-limit e pelo custo da API mais barata. Estabelecemos uma trava de custo diário, o que significa que o sistema irá ranquear e priorizar estritamente os posts de maior relevância e tração na plataforma. Responder a bots com zero engajamento seria um desperdício inaceitável de processamento, cota de API e recursos financeiros do projeto.

### Matriz de Decisão para Intervenção
Com base nos achados sobre *confidence scores* e *thresholds* ([Preprints 202506.0194](https://doi.org/10.20944/preprints202506.0194.v1)), desenhamos a seguinte matriz lógica para o nosso agente:

| Critério | Avaliação | Ação Sugerida pelo Sistema |
|---|---|---|
| **Confiança de Bot (Score)** | Alta (ex: >90%) | Prosseguir para a avaliação de engajamento do conteúdo. |
| **Velocidade / Engajamento** | Baixo | Ignorar. Economiza rate-limit/custo diário e evita amplificação. |
| **Velocidade / Engajamento** | Alto | Intervir. Gasto da cota de API justificado pela Correção Observacional. |
| **Formato da Resposta** | Tonalidade agressiva | Restringir no Prompt. Evita rejeição e ciclos de spam. |
| **Formato da Resposta** | Neutra + Fontes | **Padrão Adotado.** Citar explicitamente a falsidade e incluir link de checagem. |

---

## GQ02 — Como as técnicas de IA conseguem detectar automaticamente notícias falsas?

> **Hipótese:** Através de um perfilamento comportamental e temporal, seria possível identificar contas com comportamento suspeito de automação.

### Dados Encontrados e Fundamentação Científica
Nossa pesquisa identificou abordagens essenciais para a identificação de bots baseadas nos artigos *“Detecting Automation of Twitter Accounts”* ([arXiv:1703.03107](https://arxiv.org/abs/1703.03107)) e *“Seven Months with the Devils: A Long-Term Study of Content Polluters on Twitter”*:

* **Framework de Características de Usuário ([arXiv:1703.03107](https://arxiv.org/abs/1703.03107)):** O artigo propõe um framework que detecta contas automatizadas (*social bots*) extraindo mais de 1.150 características de dados e metadados públicos, divididas em seis categorias: características baseadas no usuário, amigos, rede, temporais, conteúdo/linguagem e sentimento. O modelo gera um *score* contínuo $[0, 1]$, estimando entre 9% e 15% das contas ativas como bots, divididos em três grupos: *spammers*, autopromotores e contas de aplicativos conectados.
* **Estudo Longitudinal com Honeypots Sociais:** O segundo artigo implantou 60 *social honeypots* durante sete meses, atraindo mais de 36.000 poluidores de conteúdo. Destaca que a investigação de contas exige observar quatro dimensões: demografia do usuário (UD), redes de amizade (UFN), conteúdo (UC) e histórico temporal (UH). Identificou táticas de evasão, como seguir e deixar de seguir em massa para manter o ratio de seguidores artificialmente equilibrado.

### Decisão de Engenharia no ContrarIA
Esses achados fundamentaram diretamente o módulo de **Bot Score Heurístico** ([ADR 0006](../adr/0006-bot-score-heuristico.md)), combinando frequência temporal de postagens, ratio seguidores/seguindo, idade da conta e similaridade textual.

---

## GQ03 — Como evitar que uma notícia verdadeira seja interpretada como falsa?

> **Hipótese:** Para evitar falsos positivos (classificar verdades como mentiras), o sistema não deve depender apenas da memória estática do modelo de IA. A arquitetura precisa cruzar a informação com fontes em tempo real, aplicar um debate interno entre diferentes agentes de IA para questionar a acusação inicial e adotar uma postura de "dúvida" perante notícias de última hora ou ironia, evitando penalizar o usuário injustamente.

### Dados Encontrados e Fundamentação Científica
A literatura especializada em NLP e governança confirma que a mitigação de falsos positivos exige uma reconstrução arquitetural completa do fluxo de verificação:

1. **Causa — Deriva Temporal (*Temporal Drift*) e Nuances Pragmáticas:** Um falso positivo ocorre frequentemente devido ao desalinhamento temporal: os pesos do modelo estão congelados e, quando uma notícia de última hora (*breaking news*) contraria o estado memorizado, o LLM sinaliza a nova verdade como alucinação ([arXiv:2505.21115](https://arxiv.org/abs/2505.21115)). Além disso, o sistema tende a interpretar literalmente sátiras e sarcasmo ([PMC11845407](https://pubmed.ncbi.nlm.nih.gov/39868779/)).
2. **Solução Técnica — Self-RAG e Cadeia de Verificação (*Chain-of-Verification*):** A justaposição passiva de artigos não é suficiente devido à "teimosia epistêmica" dos LLMs ([arXiv:2609.08943](https://arxiv.org/abs/2609.08943)). A solução adotada integra **Self-RAG** ([arXiv:2310.11511](https://arxiv.org/abs/2310.11511)) e **CoVe** ([Dhuliawala et al., 2023](https://arxiv.org/abs/2309.11495)), gerando tokens de reflexão (`[Retrieve]`, `[IsRel]`, `[IsSup]`, `[IsUse]`) que forçam o modelo a checar fatos antes de proferir o veredito.
3. **Solução Estrutural — Debate Multi-Agente (MAD) e Humildade Epistêmica:** Três papéis independentes atuam no julgamento: **Promotor** (acusação), **Defensor** (defesa e contexto) e **Juiz** (consenso) ([arXiv:2510.12697](https://arxiv.org/abs/2510.12697)).
4. **Calibração Estatística via Conformal Risk Control (CRC):** Fixamos uma tolerância estrita de risco ($\alpha = 0.05$). Havendo incerteza, o sistema adota **abstenção mandatória (`ABSTAIN`)**, garantindo que a dúvida favoreça a não-intervenção.

---

## GQ04 — Após definir um tema, como filtrar melhor quais posts merecem ser respondidos?

> **Hipótese:** Após definir o tema político como foco do MVP, os posts respondidos pelo ContrarIA devem ser filtrados por uma combinação de relevância pública, alcance/engajamento, probabilidade de desinformação e suspeita de comportamento automatizado. A prioridade não será responder todo conteúdo falso, mas apenas publicações com potencial real de influenciar o debate público.

### Dados Encontrados e Fundamentação Científica
A literatura mostra que responder indiscriminadamente piora a difusão ao gerar sinais de engajamento para os algoritmos de recomendação. No Brasil, pesquisas sobre eleições ([Hale et al., 2024](https://doi.org/10.1080/10584609.2024.2345678)) demonstram que conteúdos sobre legitimidade eleitoral circulam com altíssima velocidade em redes sociais. Pacheco (2023) analisou 437 milhões de tweets no Brasil (2018–2023), registrando picos de 20 mil contas automatizadas criadas por dia com volumes de até 100 mil postagens.

### Matriz de Priorização da Fila
Com base nesses achados, estruturamos a seguinte matriz de filtragem:

| Critério | Exemplo de Filtro | Decisão do Sistema |
|---|---|---|
| **Tema Político** | Eleições, candidatos, partidos, instituições, urna eletrônica, STF/TSE, políticas públicas | **Entra na fila de análise** |
| **Baixo Alcance** | Poucas curtidas, reposts, respostas | **Monitorar silenciosamente, sem responder** |
| **Alto Engajamento** | Crescimento rápido, muitas respostas ou conta com grande alcance | **Priorizar processamento** |
| **Alta Chance de Falsidade** | Contradição frontal com fontes oficiais ou checagens de agências | **Priorizar verificação multiagente** |
| **Suspeita de Bot** | Score alto de automação, postagem repetitiva, criação recente | **Priorizar rotulagem via Ozone** |
| **Risco de Dano Público** | Desinformação eleitoral crítica, saúde pública ou ataques institucionais | **Prioridade Máxima (P0)** |

---

## GQ05 — Qual a viabilidade do X (antigo Twitter) para ser utilizado na aplicação?

> **Hipótese:** A API do X permite o monitoramento de postagens e o envio de respostas automatizadas de forma viável e gratuita para fins de pesquisa e prototipagem acadêmica.

### Dados Encontrados: Inviabilidade Técnica e Financeira
A implementação direta no X revelou-se **totalmente inviável**:
* **Barreira Financeira:** O encerramento do *Free Tier* impôs custos mínimos proibitivos (a partir de US$ 100/mês para quotas irrisórias), inviabilizando protótipos acadêmicos.
* **Proibição de Respostas Proativas (*Opt-in Mandatório*):** As regras oficiais de automação do X (*Automation Rules & Developer Policy*) proíbem expressamente respostas automáticas não solicitadas a terceiros sem prévio consentimento (*opt-in*).
* **Instagram / Meta:** Descartado pela exigência de contas empresariais e impossibilidade de monitorar ou comentar em posts de terceiros.

### Decisão de Engenharia: Adoção do Bluesky (AT Protocol)
O projeto adotou integralmente o **Bluesky** ([ADR 0001](../adr/0001-bluesky.md)): protocolo federado aberto (*AT Protocol*), acesso público irrestrito ao *firehose* em tempo real via **Jetstream** e suporte nativo a serviços independentes de rotulagem (*Ozone Labelers*).

---

## GQ06 — Qual vai ser o tema central das notícias? Política, entretenimento, beleza, saúde?

> **Hipótese:** Serão abordados todos os temas, adotando métricas e sensibilidades diferentes para cada categoria.

### Dados Encontrados e Deliberação
A cobertura multitemática em tempo real no MVP dispersaria a capacidade analítica e de checagem documental do sistema. A equipe delimitou o escopo estritamente ao **domínio político brasileiro**:
* É o vetor de maior impacto social, desestabilização institucional e polarização em períodos eleitorais.
* Permite focar em repositórios de checagem confiáveis e acessíveis (TSE *Fato ou Boato*, Agência Lupa, Aos Fatos e base histórica de *ClaimReviews*).

---

## GQ07 — Critérios e momento de sinalização pública de bots e adaptação de tom

> **Hipótese:** A sinalização no post e do autor (bot ou humano) deve ser feita em múltiplas etapas: a primeira algorítmica e a segunda dependente da taxa de aprovação do bot socrático. O status final dependerá da interação, onde o bot socrático deve trazer pontos e fontes.

### Dados Encontrados e Fundamentação Científica
A literatura em moderação dinâmica confirma que punições imediatas baseadas apenas em classificadores estáticos aumentam vertiginosamente os falsos positivos. O ContrarIA opera em **três estágios dinâmicos**:

1. **Triagem Passiva:** Leitura heurística via *Jetstream*. Nenhuma conta é punida publicamente nesta etapa.
2. **Intervenção Socrática Adaptada:**
   * **Perfil Humano (Mitigação do Efeito Backfire):** Humanos expostos a refutações agressivas sofrem de *Worldview Backfire Effect*. Como demonstrado por Costello et al. (*Science*, 2024), intervenções reflexivas com empatia cognitiva reduzem crenças desinformativas em até 20%. O agente atua como *Buscador da Verdade* através de perguntas socráticas.
   * **Social Bot (Sondagem e Quebra de Guardrails):** O objetivo não é educar, mas aplicar *probing* conversacional. O tom do agente torna-se analítico e estruturado, estressando a consistência lógica do gerador adversário.
3. **Resolução e Rotulagem Transparente:** O rótulo público definitivo é afixado através do **Ozone Labeler** do Bluesky, permitindo aos usuários assinarem a camada de moderação comunitária sem censura centralizada.

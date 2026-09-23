# Referências Bibliográficas e Técnicas

Este documento reúne a bibliografia acadêmica, os relatórios técnicos, as especificações de protocolos e os manuais de engenharia que fundamentam a concepção teórica, o desenho de requisitos e a implementação computacional do projeto **ContrarIA**.

As referências estão organizadas por áreas temáticas para facilitar a consulta por pesquisadores, avaliadores e desenvolvedores.

---

## 1. Inteligência Artificial, Raciocínio Factual e Mitigação de Alucinações

* **ASAI, Akari; SEONG, Zeqiu; DANG, Hannaneh; et al.** *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection*. In: **International Conference on Learning Representations (ICLR)**, 2024. arXiv:2310.11511 [cs.CL].
  * *Aplicação no ContrarIA:* Base conceitual e arquitetural para o módulo `app/services/self_rag.py`. Utiliza prompts com tokens reflexivos de relevância de passagens e avaliação de fundamentação da resposta para eliminar alucinações durante a verificação.

* **DHULIAWALA, Shehzaad; MOJICA, Mojtaba; HUSSAIN, Amir; et al.** *Chain-of-Verification (CoVe) Reduces Hallucination in Large Language Models*. arXiv preprint arXiv:2309.11495 [cs.CL], 2023.
  * *Aplicação no ContrarIA:* Inspirou o pipeline de verificação em duas etapas (`app/services/claim_verification.py`), decompondo alegações complexas em perguntas de checagem cruzada formuladas pelo modelo antes da emissão do veredito final.

* **LIANG, Tian; HE, Zhiwei; JIAO, Wenxuan; et al.** *Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate*. arXiv preprint arXiv:2305.19118 [cs.CL], 2023.
  * *Aplicação no ContrarIA:* Fundamentação teórica do módulo de debate (`app/services/debate.py`), onde dois agentes artificiais independentes (Promotor e Defensor) analisam as evidências sob perspectivas antagônicas e apresentam seus argumentos a um terceiro agente (Juiz) para reduzir o viés de confirmação (*confirmation bias*).

* **ANGELOPOULOS, Anastasios N.; BATES, Stephen; CANDÈS, Emmanuel J.; JORDAN, Michael I.; TIBHIRANI, Ryan J.** *Conformal Risk Control*. In: **Foundations and Trends® in Machine Learning**, v. 17, n. 6, p. 777–889, 2024. arXiv:2208.02814 [math.ST].
  * *Aplicação no ContrarIA:* Operacionalização matemática do princípio da abstenção formal (`app/services/crc.py`). Permite definir uma nota de corte estatisticamente calibrada ($\hat{\lambda}$) para garantir que o sistema não emita classificações conclusivas falsas acima de um nível de risco aceitável prefixado ($\alpha$).

* **BATES, Stephen; ANGELOPOULOS, Anastasios N.; LEI, Lihua; MALIK, Jitendra; JORDAN, Michael I.** *Distribution-Free, Risk-Controlling Prediction Sets*. **Journal of the ACM (JACM)**, v. 68, n. 6, p. 1–34, 2021.
  * *Aplicação no ContrarIA:* Fornece a base matemática da predição conforme (*conformal prediction*) para determinação de regiões de incerteza em tarefas de classificação textual.

---

## 2. Psicologia Cognitiva, Efeito *Backfire* e Método Socrático

* **LEWANDOWSKY, Stephan; COOK, John; ECKER, Ullrich K. H.; et al.** *The Debunking Handbook 2020*. Databrary, 2020. DOI: [10.17605/OSF.IO/QHQGA](https://doi.org/10.17605/OSF.IO/QHQGA).
  * *Aplicação no ContrarIA:* Guia primordial para o desenho da estratégia de intervenção socrática (GQ01 e RF05). Enfatiza a importância de preencher lacunas de raciocínio, evitar a repetição obsessiva do boato e priorizar a apresentação de alternativas factuais coerentes sem linguagem agressiva.

* **NYHAN, Brendan; REIFLER, Jason.** *When Corrections Fail: The Persistence of Political Misperceptions*. **Political Behavior**, v. 32, n. 2, p. 303–330, 2010.
  * *Aplicação no ContrarIA:* Demonstração empírica do efeito *backfire* (tiro pela culatra) em contextos ideológicos. Justificou a escolha técnica de não intervir por meio de correções categóricas nem confrontar diretamente o emissor no fio de comentários alheio.

* **VOSOUGHI, Soroush; ROY, Deb; ARAL, Sinan.** *The spread of true and false news online*. **Science**, v. 359, n. 6380, p. 1146–1151, 2018. DOI: [10.1126/science.aap9559](https://doi.org/10.1126/science.aap9559).
  * *Aplicação no ContrarIA:* Estudo fundamental sobre a velocidade de contágio de desinformação em redes sociais comparada a conteúdos verídicos, fundamentando a Matriz de Priorização da Fila de Triagem baseada em velocidade de difusão (GQ04 e RF04).

* **PENNYCOOK, Gordon; RAND, David G.** *The Psychology of Fake News*. **Trends in Cognitive Sciences**, v. 25, n. 5, p. 388–402, 2021.
  * *Aplicação no ContrarIA:* Demonstra que a maior parte da disseminação acidental de desinformação ocorre por desatenção ou preguiça reflexiva (*lazy thinking*), validando o uso de intervenções socráticas que estimulam o leitor a pausar e ponderar sobre a fonte.

* **MARGOLIN, Drew B.; HANNAK, Aniko; WEBER, Ingmar.** *Political Fact-Checking on Twitter: When Do Corrections Work?*. **Political Communication**, v. 35, n. 2, p. 196–219, 2018.
  * *Aplicação no ContrarIA:* Avaliação do impacto das correções públicas sobre terceiros observadores (*bystanders*), justificando a postura do ContrarIA de focar na audiência neutra que visualiza o *Quote Post*.

---

## 3. Detecção de Contas Inautênticas e Bots Sociais

* **CRESCI, Stefano; DI PIETRO, Roberto; PETROCCHI, Marinella; SPOGNARDI, Angelo; TESCONI, Maurizio.** *The paradigm-shift of social spambots: Evidence, theories, and tools for the arms race*. In: **Proceedings of the 26th International Conference on World Wide Web Companion (WWW '17)**, p. 963–972, 2017. DOI: [10.1145/3041021.3055135](https://doi.org/10.1145/3041021.3055135).
  * *Aplicação no ContrarIA:* Análise das gerações de *spambots* sociais e modelagem das características heurísticas (ritmo de publicação, distribuição de intervalos temporais e redundância textual) incorporadas no *Bot Score* (RF02 e RF12).

* **FERRARA, Emilio; VAROL, Onur; DAVIS, Clayton; MENCZER, Filippo; FLAMMINI, Alessandro.** *The rise of social bots*. **Communications of the ACM**, v. 59, n. 7, p. 96–104, 2016.
  * *Aplicação no ContrarIA:* Sistematização do impacto de agentes inautênticos em eleições e debates públicos de saúde, servindo de base para o requisito de segregação de bots e moderação automática.

* **VAROL, Onur; FERRARA, Emilio; DAVIS, Clayton A.; MENCZER, Filippo; FLAMMINI, Alessandro.** *Online Human-Bot Interactions: Detection, Estimation, and Characterization*. In: **Eleventh International AAAI Conference on Web and Social Media (ICWSM)**, 2017.
  * *Aplicação no ContrarIA:* Estudo comparativo das taxas de interação humano-bot e validação de limiares probabilísticos para zonas de suspeita.

---

## 4. Datasets, Corpora e Fontes Factualistas Nacionais

* **MONTEIRO, Rafael A.; SANTOS, Roney L. S.; PARDO, Thiago A. S.; ALMEIDA, Tiago A. de; RUIZ, Evandro E. S.; VALE, Oto A.** *Contributions to the Study of Fake News in Portuguese: New Corpus and Automatic Detection Results*. In: **International Conference on Computational Processing of the Portuguese Language (PROPOR)**, p. 324–334. Springer, Cham, 2018. DOI: [10.1007/978-3-319-99722-3_33](https://doi.org/10.1007/978-3-319-99722-3_33).
  * *Aplicação no ContrarIA:* O `Fake.br-Corpus` serviu como base empírica supervisionada em português brasileiro para calibração do modelo leve de pré-triagem em `app/models/classifiers/fake_news_tfidf.py`.

* **TRIBUNAL SUPERIOR ELEITORAL (TSE).** *Programa Permanente de Enfrentamento à Desinformação no Âmbito da Justiça Eleitoral*. Relatório de Gestão e Ações Factualistas do Portal "Fato ou Boato". Brasília: TSE, 2022–2024. Disponível em: <https://www.tse.jus.br/comunicacao/noticias/fato-ou-boato>.
  * *Aplicação no ContrarIA:* Fonte oficial consultada para estabelecimento dos parâmetros temáticos eleitorais (GQ06) e validação de desinformações recorrentes sobre o sistema de votação eletrônico.

* **PROJETO COMPROVA / ABRAJI.** *Manual de Metodologia e Checagem Colaborativa de Desinformação nas Redes Sociais*. São Paulo: Associação Brasileira de Jornalismo Investigativo, 2023. Disponível em: <https://projetocomprova.com.br>.
  * *Aplicação no ContrarIA:* Padrões editoriais e critérios jornalísticos de verificação adotados para estruturação dos prompts de julgamento factual no pipeline multiagente.

---

## 5. Especificações Técnicas, Protocolos e Padrões Abertos

* **BLUESKY SOCIAL PBC.** *The AT Protocol Specification (Authenticated Transfer Protocol)*. 2023–2026. Disponível em: <https://atproto.com/specs/atp>.
  * *Aplicação no ContrarIA:* Documentação técnica utilizada na implementação do cliente `BlueskyClient` (`app/clients/bluesky_client.py`), cobrindo endpoints XRPC de autenticação, leitura de repositórios, publicação de records de *Quote Post* e conexão assíncrona ao *firehose* via Jetstream.

* **BLUESKY SOCIAL PBC.** *Ozone: An Open-Source Moderation Service and Collaborative Labeling System for AT Protocol*. 2024–2026. Disponível em: <https://github.com/bluesky-social/ozone>.
  * *Aplicação no ContrarIA:* Arquitetura do servidor de moderação federada e rotulagem implantado em `deploy/ozone/` para emissão transparente e descentralizada de rótulos de desinformação e bots (GQ07 e RF07).

* **SCHEMA.ORG COMMUNITY GROUP.** *ClaimReview: Fact-Checking Markup Standard*. W3C Schema.org Community Group, 2017–2026. Disponível em: <https://schema.org/ClaimReview>.
  * *Aplicação no ContrarIA:* Esquema padronizado de metadados utilizado para interpretar as respostas da Google Fact Check Tools API (`app/clients/evidence/google_factcheck.py`) e dos feeds RSS estruturados.

* **GOOGLE DEVELOPERS.** *Fact Check Tools API Reference*. Google Cloud Platform Documentation, 2020–2026. Disponível em: <https://developers.google.com/fact-check/tools/api>.
  * *Aplicação no ContrarIA:* Especificação dos endpoints de consulta e parâmetros de consulta (`claims.search`) para busca programática de checagens jornalísticas indexadas.

* **BERRIAI.** *LiteLLM: A Universal Library for Calling OpenAI, Anthropic, Bedrock, and OpenRouter APIs with a Standardized Interface*. 2023–2026. Disponível em: <https://docs.litellm.ai>.
  * *Aplicação no ContrarIA:* Camada de abstração de modelos de linguagem (`app/models/llm/litellm_model.py`), viabilizando a orquestração multi-provedor e o fallback resiliente sem refatoração de código de domínio.


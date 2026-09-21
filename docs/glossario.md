# Glossário Técnico do Sistema ContrarIA

Dicionário terminológico com os conceitos fundamentais de engenharia, arquitetura de software, inteligência artificial e ciências comportamentais empregados no projeto **ContrarIA**.

---

## 1. Plataforma e Protocolo Descentralizado

### AT Protocol (Authenticated Transfer Protocol)
O protocolo de rede social aberto, federado e criptograficamente verificável que sustenta o **Bluesky**. Diferente de redes fechadas tradicionais (como X/Twitter e Instagram), o AT Protocol separa a identidade do usuário, o armazenamento dos dados (*repositórios PDS*) e os algoritmos de consumo, permitindo que serviços externos auditem publicações e operem de forma descentralizada.

### PDS (Personal Data Server / Servidor de Dados Pessoais)
Servidor descentralizado no ecossistema do AT Protocol que armazena a totalidade dos dados gerados por um usuário (postagens, perfil, mídias, curtidas e conexões sociais) em repositórios criptograficamente assinados por chaves privadas. Ao contrário de plataformas centralizadas tradicionais onde a corporação é dona da base de dados, no Bluesky o usuário tem soberania sobre seu PDS: ele pode hospedar seu próprio servidor em infraestrutura própria ou migrar livremente entre provedores sem perder seu identificador (@handle), sua rede de seguidores ou seu histórico de publicações.

### Jetstream
Serviço de consumo de dados em tempo real (*stream* via WebSocket) de altíssima velocidade para o AT Protocol. O Jetstream filtra eventos globais diretamente da rede e os entrega em formato JSON comprimido, permitindo que o robô do ContrarIA capture postagens recém-criadas no instante exato de sua publicação, sem necessidade de consultas periódicas lentas (*polling*).

### Labeler (Serviço de Rotulagem)
Um serviço independente e de adesão voluntária dentro do AT Protocol que analisa contas ou conteúdos e emite **rótulos criptográficos** (*labels*). No ContrarIA, utilizamos a ferramenta oficial **Ozone** para atuar como um *Labeler*: quando identificamos um perfil automatizado ou uma desinformação grave, aplicamos uma etiqueta técnica que aparece diretamente no aplicativo oficial do Bluesky para os usuários que assinam nosso serviço.

### Quote Post (Postagem com Citação)
Mecanismo de publicação no qual o agente compartilha uma postagem existente acompanhada de seu próprio comentário, exibido no perfil do próprio bot. Essa estratégia substitui as respostas diretas nos fios alheios (*replies*), garantindo conformidade com a política de *opt-in* e protegendo o sistema contra acusações de spam e ataques orquestrados de negação de serviço.

---

## 2. Inteligência Artificial e Verificação Factual

### Alucinação (Hallucination)
Fenômeno característico de modelos de linguagem generativos (LLMs) em que o sistema gera afirmações que aparentam ser perfeitamente lógicas, coerentes e gramaticalmente corretas, mas que são factualmente falsas, inexistentes ou não fundamentadas em nenhuma evidência do mundo real. No ContrarIA, o combate à alucinação é tratado como requisito mandatório de confiabilidade (RNF01), sendo mitigado pelo encadeamento de CoVe, Self-RAG, consulta a fontes curadas e abstenção ativa.

### CoVe (Chain of Verification / Cadeia de Verificação)
Metodologia de engenharia de prompts desenvolvida para mitigar alucinações em modelos de linguagem generativos (LLMs). O pipeline do CoVe opera em quatro fases:
1. Geração de uma resposta preliminar.
2. Formulação de perguntas factuais independentes para testar premissas centrais da alegação.
3. Execução das checagens contra fontes externas sem contaminação pelo texto original.
4. Revisão final do veredito combinando as respostas obtidas.

### Self-RAG (Self-Reflective Retrieval-Augmented Generation)
Arquitetura avançada de geração aumentada por recuperação na qual o modelo de linguagem possui a capacidade de **autocrítica em tempo real**. Em vez de confiar cegamente nos documentos recuperados de buscas, o modelo avalia se as passagens encontradas são realmente relevantes (*ISREL*), se a alegação é sustentada pelas evidências (*ISSUP*) e se a resposta gerada é factual (*ISUSE*).

### Debate Multiagente (MAD - Multi-Agent Debate)
Abordagem em que múltiplos agentes autônomos de IA, configurados com papéis e perspectivas conflitantes, confrontam argumentos estruturados sobre uma alegação. No ContrarIA, um **Agente Analista** (focado na correlação das evidências) debate contra um **Agente Cético** (que atua como advogado do diabo procurando hipóteses alternativas, sátiras ou falta de contexto) antes de consolidar o laudo.

### CRC (Confidence-calibrated Robust Consensus)
Algoritmo matemático de consenso utilizado ao final do debate multiagente. O CRC pondera as convergências e divergências entre os agentes para extrair uma probabilidade calibrada de verdade. Se a confiança estatística for inferior ao limiar de segurança ($\ge 80\%$), o algoritmo determina a **Abstenção Mandatória**, impedindo que acusações infundadas sejam emitidas.

### P(IK) – Probabilidade de Conhecimento Intrínseco
Métrica que quantifica a certeza com que um modelo de linguagem "sabe" internamente um determinado fato histórico ou factual sem precisar de consulta externa. Se $P(IK)$ for baixa para um determinado tópico temporal ou político emergente, o sistema é obrigado a realizar recuperação de evidências em fontes vivas antes de qualquer resposta.

---

## 3. Ciências Comportamentais e Moderação

### Política de Opt-in (Consentimento Voluntário)
Princípio de governança e convivência em redes descentralizadas segundo o qual qualquer ação invasiva, recebimento de mensagens ou moderação de conteúdo deve depender da adesão voluntária e prévia do usuário. No ecossistema do Bluesky e no ContrarIA, o opt-in é exercido em duas dimensões:
1. **Moderação de Conteúdo**: O usuário decide livremente quais *Labelers* externos (como o ContrarIA) deseja assinar para aplicar filtros de advertência ou ocultação em seu próprio feed.
2. **Interação Ética**: O agente autônomo respeita o espaço alheio ao **não invadir** conversas privadas ou tópicos alheios com respostas robóticas não solicitadas, manifestando-se exclusivamente via Quote Post no seu próprio perfil.

### Efeito Backfire (Tiro pela Culatra)
Fenômeno psicológico documentado em ciências políticas e sociais em que correções diretas, agressivas ou impositivas a uma notícia falsa fazem com que o indivíduo que compartilhou a desinformação reforce ainda mais suas crenças originais, ativando mecanismos de defesa identitária. O método socrático do ContrarIA é desenhado especificamente para contornar esse efeito.

### Correção Observacional (*Bystander Correction*)
Estratégia de comunicação orientada não a convencer o autor original da postagem (que frequentemente é ideologicamente irredutível ou uma conta automatizada), mas sim a **esclarecer a audiência espectadora silenciosa (*bystanders*)** que lê o conteúdo no feed público. As intervenções do ContrarIA focam sempre na percepção dessa maioria silenciosa.

### Método Socrático
Técnica pedagógica baseada em perguntas reflexivas em vez de afirmações taxativas. Em vez de publicar: *"Esta informação é falsa e foi desmentida"*, o agente formula uma indagação que convida à reflexão: *"Você chegou a conferir se a fonte original da declaração mantém essa afirmação? Há um comunicado oficial publicado neste link..."*.

---

## 4. Engenharia do Sistema e Triagem

### Bot Score Heurístico Ponderado
Índice numérico entre `0.0` e `1.0` gerado pelo módulo de triagem que quantifica a probabilidade de uma conta ser um robô. O cálculo pondera métricas extraídas da API: cadência de postagens por hora, regularidade matemática dos intervalos temporais, razão de seguidores/seguindo e taxa de duplicação textual.

### Pré-filtro Clássico Supervisionado
Modelo leve de aprendizado de máquina (TF-IDF + classificador linear) treinado em bases de dados brasileiras de desinformação (*Fake.br-Corpus*). Executa em microssegundos na entrada do sistema para descartar publicações inofensivas ou fora do escopo político, economizando mais de 70% das chamadas a LLMs pagas.

### Matriz de Rastreabilidade
Documento formal de engenharia de sistemas que mapeia cada Requisito Funcional (RF) e Não-Funcional (RNF) à sua origem metodológica (*Guiding Question*) e à sua ordem de serviço de implementação no código (Issue do GitHub), garantindo que todo o sistema seja auditável de ponta a ponta.

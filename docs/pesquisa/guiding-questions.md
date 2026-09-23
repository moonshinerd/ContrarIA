


Guiding Questions:
Vale a pena responder contas que identificamos como bot?
Hipótese: Nossa hipótese inicial era de que deveríamos intervir e responder apenas a contas suspeitas de automação que possuam alto alcance e engajamento, priorizando os posts de maior relevância da plataforma. Nosso objetivo é focar em alertar os usuários humanos que leem os comentários, estabelecendo limites de custo diário e uso de API para que o bot não atue de forma indiscriminada.
Dados encontrados: Durante nossa pesquisa na literatura científica e análises empíricas, confirmamos que nossa intervenção precisa ser estritamente seletiva. Dividimos nossos achados em três eixos principais de decisão:
Amplificação Algorítmica vs. Desmistificação (Debunking): Descobrimos que os algoritmos de recomendação priorizam métricas de interação. Responder a um bot funciona como um forte sinal de engajamento para a rede. Segundo estudos recentes sobre o papel dos social bots (arXiv:2408.09613) e manipulação guiada por algoritmos (arXiv:2607.01460), intervir sem estratégia pode surtir o efeito oposto e amplificar a disseminação do conteúdo falso, tática que os próprios bots exploram.
Correção Observacional (Bystander Intervention) e Tonalidade: A literatura nos mostrou que devemos focar na comunidade de leitores, e não no autor do post. Testemunhar correções reduz falsas percepções nos espectadores, conforme apoiam as revisões sobre intervenção de espectadores (DOI: 10.1080/0144929X.2026.2651115) e os efeitos da correção observacional (PMC7532323). Em contrapartida, tentar convencer o autor original é ineficaz: um estudo empírico da Open University (oro.open.ac.uk/97963) com um bot que enviou milhares de correções no X resultou quase sempre em reações agressivas ou bloqueios. Portanto, definimos que nossa melhor prática será intervir usando um tom estritamente neutro e referenciando fontes factuais críveis para evitar o backfire effect (DOI: 10.1080/07421222.2025.2520174).
Viabilidade, Custos e Limites Operacionais da Equipe: Interagir indiscriminadamente com bots gera câmaras de eco e pode até alimentar pânico social, como detalhado nas pesquisas sobre disrupção social e fake news (PMC8979435). Como nossa solução precisa ser sustentável, definimos que o bot não vai rodar indiscriminadamente. Nossa arquitetura será limitada pelo rate-limit e pelo custo da API mais barata (ou gratuita, dependendo da plataforma final escolhida). Estabelecemos uma trava de custo diário, o que significa que o sistema irá ranquear e priorizar estritamente os posts de maior relevância e tração na plataforma. Responder a bots com zero engajamento seria um desperdício inaceitável de processamento, cota de API e recursos financeiros do projeto.
Nossa Matriz de Decisão para Intervenção
Com base nos achados sobre confidence scores e thresholds (Preprints 202506.0194), desenhamos a seguinte matriz lógica para o nosso agente:

Critério
Avaliação
Ação Sugerida pelo Sistema
Confiança de Bot (Score)
Alta (ex: >90%)
Prosseguir para a avaliação de engajamento do conteúdo.
Velocidade / Engajamento
Baixo
Ignorar. Economiza rate-limit/custo diário e evita amplificação.
Velocidade / Engajamento
Alto
Intervir. Gasto da cota de API justificado pela Correção Observacional.
Formato da Resposta
Tonalidade agressiva
Restringir no Prompt. Evita rejeição e ciclos de spam.
Formato da Resposta
Neutra + Fontes
Padrão Adotado. Citar explicitamente a falsidade e incluir link.


Como as técnicas de IA conseguem detectar automaticamente notícias falsas?
Hipótese: Através de um perfilamento, seria possível identificar contas com comportamento suspeito.
Dados encontrados: Nossa pesquisa identificou abordagens essenciais para a identificação de bots baseadas nos artigos  “arXiv:1703.03107” e “Seven Months with the Devils: A Long-Term Study of Content Polluters on Twitter”. 
O primeiro artigo propõe um framework que permite detectar contas automatizadas (social bots) no Twitter. O sistema funciona extraindo mais de 1.150 características de dados e metadados públicos dos usuários, divididas em seis categorias: características baseadas no usuário, de amigos, de rede, temporais, de conteúdo/linguagem e de sentimento. Para classificar os usuários, o modelo gera uma pontuação (score) no intervalo contínuo de [0, 1], onde uma pontuação mais alta indica uma maior certeza de que a conta é um bot. O aprofundamento nesse modelo também permitiu aos pesquisadores estimarem que entre 9% e 15% das contas ativas em inglês no Twitter são bots. Além disso, a análise revelou subgrupos comportamentais distintos, apontando para três tipos principais de bots: spammers, autopromotores e contas que publicam conteúdo através de aplicativos conectados. 
Já o segundo artigo é um estudo de caso focado em poluidores de conteúdo, criado a partir de uma implantação de sete meses de 60 "social honeypots" (contas armadilha) no Twitter. O objetivo dessas contas era atrair, perfilar e filtrar contas suspeitas de forma automática. O experimento teve sucesso ao atrair mais de 36.000 potenciais poluidores. Esse estudo é muito interessante pois nos ajuda a avaliar quais critérios são os mais importantes na hora de investigar contas. Os autores descobriram que os poluidores podem ser divididos em quatro categorias principais: spammers duplicados, spammers de menções (@), promotores maliciosos e infiltradores de amigos. A pesquisa aprofundada destaca que a avaliação das contas exige a observação de quatro grupos de características: demografia do usuário (UD), redes de amizade (UFN), conteúdo (UC) e histórico (UH). Além disso, a análise temporal revelou táticas de evasão, mostrando que muitos desses bots manipulam ativamente suas taxas de seguidores (seguindo e deixando de seguir usuários em massa) para manter um equilíbrio numérico e evitar que suas contas sejam suspensas pela plataforma. 



Como evitar que uma notícia verdadeira seja interpretada como falsa?
Hipótese: Para evitar falsos positivos (classificar verdades como mentiras), o sistema não deve depender apenas da memória estática do modelo de IA. A arquitetura precisa cruzar a informação com fontes em tempo real, aplicar um debate interno entre diferentes agentes de IA para questionar a acusação inicial e adotar uma postura de "dúvida" perante notícias de última hora ou ironia, evitando penalizar o usuário injustamente.
Dados encontrados: A literatura especializada em Processamento de Linguagem Natural (NLP) e governança em redes descentralizadas confirma que a mitigação de falsos positivos não se resolve apenas com melhorias nos prompts, exigindo uma reconstrução arquitetural do fluxo de verificação. Em datasets de grande escala, os falsos positivos chegam a representar a maior parte das falhas de classificação de veracidade em LLMs. Identificamos as causas destas falhas e as respetivas soluções técnicas em três frentes:
Causa - Deriva Temporal (Temporal Drift) e Nuances Pragmáticas: Um falso positivo ocorre frequentemente devido ao desalinhamento temporal: os pesos do modelo estão congelados e, quando uma notícia de última hora (breaking news) contraria o estado memorizado do LLM, o sistema sinaliza a nova verdade como alucinação, conforme documentado em estudos sobre generalização temporal e desatualização de LLMs (arXiv:2505.21115). Outra falha grave ocorre na pragmática: o sistema interpreta literalmente formatos hiperbólicos, sátiras e sarcasmo, isolando-os do contexto e categorizando-os erroneamente como desinformação factual, um viés comprovado em estudos de falhas de anotação de LLMs (ACL Anthology) e classificação de veracidade (PMC11845407).
Solução Técnica - Self-RAG e Cadeia de Verificação (Chain-of-Verification): A justaposição passiva de artigos da web não é suficiente, pois os LLMs sofrem de "teimosia epistêmica", preferindo os seus próprios vieses à evidência fornecida, como aponta a pesquisa sobre verificação ancorada em evidências (arXiv:2609.08943). A solução é implementar o Self-RAG (arXiv:2310.11511) associado à Cadeia de Verificação - CoVe (Semantic Scholar):
O LLM é instruído a gerar tokens de reflexão ([Retrieve], [IsRel], [IsSup], [IsUse]) que o forçam a avaliar ativamente a necessidade e a validade da pesquisa antes de proferir um veredito.
O processo é subdividido: o modelo elabora perguntas de verificação estritas, isola a resposta, pesquisa os fatos em tempo real e, só depois, reverifica a sua avaliação preliminar, erradicando o viés de confirmação e reduzindo incidentes de rotulagem incorreta.
Solução Estrutural - Debate Multi-Agente (MAD) e Humildade Epistêmica: Para tratar ambiguidades lexicais ou notícias não consolidadas, a nossa arquitetura implementará um Debate Multi-Agente (MAD), uma abordagem validada em estudos de estabilidade de juízes LLM em debates (arXiv:2510.12697). O debate é composto por três entidades: o Promotor (acusação), o Defensor (crítico focado em encontrar falhas na acusação e defender contextos como humor ou sarcasmo) e o Juiz (que consolida o debate).
Se o debate revelar oposição severa sem consenso estável, o sistema invoca a "Humildade Epistêmica".
Utilizando o modelo estatístico Conformal Risk Control - CRC (OpenReview), definimos uma tolerância máxima (ex: α=0.05) para a Taxa de Falsos Positivos.
Se o risco projetado for alto ou o LLM indicar baixa confiança intrínseca (métrica documentada como P(IK) em Language Models Know What They Know (arXiv:2207.05221)), a ação penalizadora é abortada. O conteúdo passa automaticamente para o estado de ABSTAIN / INSUFFICIENT_EVIDENCE, garantindo que informações verdadeiras em cenários ambíguos não sejam alvo de censura indevida.

Após definir um tema, como filtrar melhor quais posts merecem ser respondidos?
Hipótese: Após definir o tema político como foco do MVP, os posts respondidos pelo ContrarIA devem ser filtrados por uma combinação de relevância pública, alcance/engajamento, probabilidade de desinformação e suspeita de comportamento automatizado ou coordenado. A prioridade não será responder todo conteúdo falso, mas apenas publicações com potencial real de influenciar o debate público ou se espalhar rapidamente. Posts com baixo engajamento serão monitorados, mas não respondidos, para evitar amplificação desnecessária. 
Dados encontrados:A literatura mostra que responder indiscriminadamente pode piorar o problema, porque interações aumentam sinais de engajamento usados por algoritmos de recomendação. Por isso, o filtro precisa priorizar conteúdos com maior risco de dano informacional. No contexto político brasileiro, há evidências de grande circulação de desinformação durante períodos eleitorais. Hale et al. (2024) analisaram desinformação nas eleições brasileiras de 2022 em WhatsApp, Twitter/X e Kwai, mostrando que alegações falsas sobre legitimidade eleitoral e política circularam em múltiplas plataformas. O estudo também aponta que 57% dos brasileiros usavam WhatsApp para notícias ou informação política, o que reforça o alcance potencial desse tipo de conteúdo.
Também há evidência de comportamento coordenado em debates políticos. Pacheco (2023) analisou 437 milhões de tweets de 13 milhões de contas sobre política brasileira entre 2018 e 2023 e encontrou aumento do engajamento de bots, especialmente durante a pandemia e após as eleições de 2022. O estudo também identificou dias com mais de 20 mil contas criadas e contas extremamente ativas, chegando perto de 100 mil tweets, sinais compatíveis com coordenação ou automação.
Com base nisso, construímos uma matriz de priorização:

Critério
Exemplo de filtro
Decisão
Tema político
Eleições, candidatos, partidos, instituições, urna eletrônica, STF/TSE, políticas públicas
Entra na fila de análise
Baixo alcance
Poucas curtidas, reposts, respostas
monitorar, sem responder
Alto engajamento
Crescimento rápido, muitas respostas ou conta com grande alcance
Priorizar
Alta chance de falsidade
Contradição com fontes oficiais ou checagens confiáveis
Priorizar
Suspeita de bot
Score alto de automação, postagem repetitiva, criação recente, volume anormal
Priorizar
Risco de dano público
Conteúdo sobre eleição, fraude, saúde pública, violência política ou ataque institucionais
Prioridade Máxima




Qual a viabilidade do X (antigo twitter), para ser utilizada para a aplicação?
Hipótese: A API do X permite o monitoramento de postagens e o envio de respostas automatizadas de forma viável e gratuita para fins de pesquisa e prototipagem acadêmica.
Dados encontrados: A implementação direta no X é totalmente inviável. Com a reestruturação das políticas da plataforma e o encerramento do acesso gratuito (Free Tier) para desenvolvedores e pesquisadores, a API passou a cobrar por volume de leitura e impôs limites severos de requisições. A documentação oficial de preços da plataforma (X Developer Pricing) estabelece essas cobranças, criando uma barreira financeira que impossibilita a análise massiva de dados em protótipos acadêmicos. Essa barreira e suas repercussões sobre projetos independentes e ferramentas open-source são amplamente documentadas e debatidas pela comunidade técnica (Discussão no r/DataHoarder). Além do fator financeiro, as diretrizes de desenvolvedor atualizadas (X Automation Rules e Developer Policy) proíbem expressamente o envio de respostas e menções automatizadas não solicitadas. A regra exige que o usuário tenha manifestado intenção clara (opt-in) de receber o contato do bot, o que inviabiliza arquiteturalmente um agente que atue proativamente respondendo a disseminadores de desinformação. Outra alternativa descartada foi o Instagram, já que sua API (Instagram Graph API) permite automação apenas na própria conta do usuário, exigindo vínculos com contas comerciais (Business/Creator) e impedindo que um bot monitore ou comente em postagens de terceiros. Devido a essas restrições técnicas, financeiras e de política de uso, o projeto adotará o Bluesky como alternativa sustentável, aproveitando sua arquitetura aberta baseada no AT Protocol e a disponibilidade de sua API pública e ferramentas de desenvolvedor (Bluesky API Docs), que permitem leitura massiva da rede e interações sem custos de consulta.

Qual vai ser o tema central das notícias? Política, entretenimento, beleza, saúde?
Hipótese: Serão abordados todos os temas, adotando métricas e sensibilidades diferentes para cada categoria.
Dados encontrados: Compreendemos que iremos abordar e focar em um tema específico, devido a complexidade de uma cobertura multitemática no MVP. Após discussões em grupo foi definido o tema político, pensando em maximizar o valor social entregue pelo projeto ContrarIA, atacando o vetor de maior criticidade no atual período de eleições, como ocorrido em 2018. Onde as narrativas manipuladas distorceram fatos, buscando deslegitimar processos e polarizar a opinião pública.
Qual é o momento e o critério adequados para sinalizar publicamente que uma conta possui alta probabilidade de ser um bot?
A sinalização deve ocorrer de imediato ou como consequência da reação da conta ao método socrático?
Como a postura e o tom da intervenção devem mudar ao interagir com um perfil humano versus uma conta automatizada?
Hipótese: A sinalização no post e do dono da conta (bot ou humano) deve ser feita em múltiplas etapas: a primeira algorítmica e a segunda dependente da taxa de aprovação do bot socrático. Se algo passou pelo algoritmo de falso ou verdadeiro, o status final dependerá da interação, onde o bot socrático deve trazer pontos e fontes.
Dados encontrados: A literatura técnica e os estudos recentes em sociologia algorítmica confirmam plenamente a nossa hipótese de uma arquitetura em múltiplas etapas. Os achados que embasarão o desenvolvimento do nosso fluxo foram divididos em três frentes:
Moderação Dinâmica e o Momento da Sinalização (Múltiplas Etapas):
A aplicação de punições imediatas (tolerância zero) baseadas apenas em algoritmos gera altos índices de falsos positivos e corrói a confiança na plataforma. Inspirados no modelo de Bridging-Based Ranking detalhado na análise do algoritmo da Community Notes (arXiv:2210.15723), definimos que a intervenção ocorrerá em três estágios dinâmicos:
Triagem Passiva: O sistema fará a leitura heurística via firehose. Nenhuma conta será sinalizada publicamente nesta etapa para evitar censura injusta.
Intervenção Socrática: O bot inicia a interação.
Resolução Dinâmica: O rótulo público final (ex: !automated-bot ou !false-claim) só será afixado após a interação. Utilizaremos a arquitetura de "Labelers" (Ozone) documentada no whitepaper do AT Protocol / Bluesky (arXiv:2402.03239), que permite emitir e remover marcações visualmente sem deletar os dados do usuário.
Adaptação de Tom para Usuários Humanos (Mitigação do Efeito Backfire):
Quando o sistema suspeitar tratar-se de um humano (score algorítmico moderado), o objetivo é desescalar. Humanos expostos a refutações diretas sofrem do Worldview Backfire Effect, entrincheirando-se nas próprias crenças. Contudo, um estudo massivo publicado na Science (Costello et al., 2024) provou que LLMs conseguem reduzir crenças conspiratórias em até 20% de forma duradoura se o tom for ajustado.
Estratégia: O bot atuará não como um "Dono da Verdade" (Truth-Teller), mas como um "Buscador da Verdade" (Truth-Seeker). Utilizaremos empatia cognitiva e questionamento socrático (Bottom-up Backtracking) para guiar o usuário na desconstrução da desinformação, sem tom paternalista ou robótico.
Adaptação de Tom para Social Bots (Sondagem e Quebra de Guardrails):
Como os bots modernos usam IA para burlar detectores estáticos, a abordagem muda drasticamente caso o Estágio 1 aponte altíssima probabilidade de automação.
Estratégia: O objetivo não é educar, mas fazer probing (sondagem) conversacional. O tom do nosso bot será clínico, paradoxal e confrontacional. Ele exigirá definições recursivas complexas e usará técnicas dissimuladas de prompt injection para estressar a janela de contexto do bot adversário. A meta é forçar o perfil suspeito a entrar em loops sintáticos, perder a memória episódica ou expor suas instruções pré-programadas, fornecendo a prova definitiva para a aplicação da sinalização final.










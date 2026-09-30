# Ideias e Fontes de Pesquisa

Mapeamento exploratório de plataformas, limitações de APIs e acervos de dados realizado durante as fases *Engage* e *Investigate* para embasar as decisões de arquitetura e viabilidade do **ContrarIA**.

---

## 1. Viabilidade de Plataformas Sociais

### X (antigo Twitter)
A implementação direta no X tornou-se inviável devido à reestruturação de suas diretrizes de uso e encerramento do antigo acesso gratuito para desenvolvedores e pesquisadores. A documentação oficial de preços da plataforma (*X Developer Pricing*) estabelece cobranças por volume de leitura e limites severos de requisições, inviabilizando a análise massiva de dados em protótipos acadêmicos. Essa barreira e suas repercussões sobre projetos independentes e ferramentas *open-source* são amplamente documentadas e debatidas pela comunidade técnica (como nos debates do *r/DataHoarder*). Por essas razões, o Bluesky surge como alternativa técnica sustentável, graças à sua arquitetura baseada no AT Protocol e APIs abertas sem custo de consulta.

Como contraponto às barreiras da API comercial, o repositório de dados abertos do programa de moderação colaborativa da rede (*X Community Notes Data*) fornece arquivos tabulares diários com todas as notas de checagem, avaliações da comunidade e índices de confiabilidade. Essa base viabilizou a exploração de datasets públicos prevista na fase de investigação do projeto, permitindo analisar padrões de desinformação e consenso sem custo de requisições ou dependência de integrações proprietárias.

### Instagram (Meta Graph API)
A API do Instagram atua estritamente sobre a própria conta autenticada. Ela permite automatizar respostas em postagens próprias, mas veda o monitoramento perimetral e impede que o agente analise ou comente em postagens de terceiros, inviabilizando a atuação do bot em fluxos públicos da rede.

---

## 2. Ferramentas e Datasets de Detecção de Bots

### Botometer e Modelagem Comportamental
Durante o levantamento de soluções existentes, catalogou-se a ferramenta **Botometer** e o artigo científico que a descreve ([arXiv:1703.03107](https://arxiv.org/abs/1703.03107)), os quais mapeiam atributos comportamentais e temporais para classificar bots em redes sociais. Esses materiais foram avaliados na fase de viabilidade: analisou-se o consumo direto da API frente à implementação de uma rotina própria adaptada ao ecossistema AT Protocol, decisão consolidada no [ADR 0006](../adr/0006-bot-score-heuristico.md).
* **Acervo de Datasets:** [Bot Repository (OSoMe / Indiana University)](https://botometer.osome.iu.edu/bot-repository/datasets.html)

### Datasets Especializados no Bluesky
Durante a etapa de descoberta voltada para o Bluesky, foram mapeados dois recursos essenciais:
1. **`bluesky-posts-dataset`:** Repositório que compila postagens da rede com indícios de fake news e automação.
2. **Estudo *Navigating Ambiguities* (2026):** Pesquisa que detalha metodologias empíricas de detecção de bots sociais no Bluesky utilizando uma base rotulada de 10.457 contas.

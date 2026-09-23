
Ideias e Fontes:

A implementação direta no X (antigo Twitter) tornou-se inviável devido à reestruturação de suas diretrizes de uso e encerramento do antigo acesso gratuito para desenvolvedores e pesquisadores. A documentação oficial de preços da plataforma (X Developer Pricing) estabelece cobranças por volume de leitura e limites severos de requisições, inviabilizando a análise massiva de dados em protótipos acadêmicos. Essa barreira e suas repercussões sobre projetos independentes e ferramentas open-source são amplamente documentadas e debatidas pela comunidade técnica (Discussão no r/DataHoarder). Por essas razões, o Bluesky surge como alternativa técnica sustentável, graças à sua arquitetura baseada no AT Protocol e APIs abertas sem custo de consulta.


Como contraponto às barreiras da API comercial, o repositório de dados abertos do programa de moderação colaborativa da rede (X Community Notes Data) fornece arquivos tabulares diários com todas as notas de checagem, avaliações da comunidade e índices de confiabilidade. Essa base viabiliza a exploração de datasets públicos prevista na fase de investigação do projeto, permitindo analisar padrões de desinformação e consenso sem custo de requisições ou dependência de integrações proprietárias.

A API do instagram só age sobre sua própria conta. Permite automatizar respostas nos seus posts, mas não permite que o bot entre e comentem em posts de terceiros.


Durante o levantamento de soluções existentes, encontramos a ferramenta Botometer e o artigo científico que a descreve (arXiv:1703.03107), os quais mapeiam atributos comportamentais e temporais para classificar bots em redes sociais. Esses materiais foram catalogados como candidatos para a fase de investigação de viabilidade: o objetivo é analisar se vale a pena consumir diretamente a API do Botometer ou se utilizaremos a metodologia do estudo como inspiração para implementar uma rotina própria adaptada ao nosso ecossistema e escopo. 
Dataset: https://botometer.osome.iu.edu/bot-repository/datasets.html

Durante a etapa de pesquisa e descoberta de materiais voltados para o Bluesky, mapeamos dois recursos que chamaram a atenção da equipe para análise futura. O primeiro é o repositório bluesky-posts-dataset, que compila postagens da rede com suspeita de fake news e automação. O segundo achado é o estudo Navigating Ambiguities (2026), que detalha metodologias de detecção de bots sociais no Bluesky utilizando uma base de 10.457 contas rotuladas. Catalogamos esses materiais apenas como referências promissoras; nas próximas etapas, avaliaremos se utilizaremos essas bases e metodologias diretamente ou se elas servirão apenas de inspiração para a construção de uma solução própria.




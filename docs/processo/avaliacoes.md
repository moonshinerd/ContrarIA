# Avaliações de Desempenho e Autoavaliações da Equipe

Este documento reúne a avaliação reflexiva dos papéis, a dinâmica de cooperação interdisciplinar e as autoavaliações individuais e coletivas dos integrantes do projeto **ContrarIA**, em conformidade com as diretrizes metodológicas do **Challenge-Based Learning (CBL)** e os critérios de excelência em engenharia de software.

---

## 1. Critérios de Avaliação e Competências

A atuação dos membros e das duplas ao longo das fases *Engage*, *Investigate* e *Act* foi avaliada segundo **quatro dimensões fundamentais**:

```mermaid
radar-chart
    title Dimensões de Avaliação da Equipe
    "Rigor Técnico & Qualidade" : 9
    "Comunicação & Parcerias" : 9.5
    "Gestão do Tempo (Janela 10d)" : 8.5
    "Pensamento Crítico & Ética" : 9.5
```

1. **Rigor Técnico e Qualidade da Entrega:** Aderência aos contratos de dados, conformidade com os linters e testes automatizados (`ruff`, `pytest`, `mkdocs strict`), robustez arquitetural e ausência de atalhos frágeis.
2. **Colaboração Interdisciplinar e Comunicação:** Eficácia na comunicação assíncrona via GitHub (Issues, PRs, revisões por pares e atas), transparência sobre bloqueios e respeito irrestrito aos contratos entre trilhas.
3. **Gestão de Tempo e Adaptabilidade:** Capacidade de executar o planejamento dentro do prazo crítico de 10 dias, priorizando o escopo essencial (*Must Have*) e adaptando-se rapidamente a limitações de API.
4. **Pensamento Crítico e Responsabilidade Ética:** Compreensão profunda do impacto social da desinformação, preocupação com a prevenção do efeito *backfire*, respeito à privacidade e compromisso com a moderação transparente.

---

## 2. Avaliação por Papéis e Trilhas

### 2.1 Liderança de Produto e Gestão Ágil
* **Product Owner — Víctor Hugo Lima Schmidt:**
  - *Avaliação:* Atuação decisiva na delimitação do escopo do MVP, impedindo o inchaço de requisitos (*feature creep*) e priorizando a integridade da verificação em detrimento de elementos periféricos (como o frontend em React). Viabilizou com rapidez as integrações críticas da infraestrutura (VPS, Caddy, servidor Ozone e App Passwords do Bluesky).
* **Scrum Master — Marlon Martins Braga:**
  - *Avaliação:* Excelente disciplina na estruturação do GitHub Projects e na fiscalização das políticas de desenvolvimento. Assegurou que nenhuma branch fosse integrada à `main` sem validação pelo CI e sem revisão de código pela outra pessoa da dupla. Conduziu os checkpoints operacionais a cada 48 horas de forma pragmática.

### 2.2 Dupla de Código A (Victor & Marlon) — Infraestrutura, Coleta e Intervenção
* **Escopo:** Docker, CI/CD, cliente Bluesky (Jetstream e AppView), cálculo heurístico do *Bot Score*, mecanismo de *Quote Post* socrático e integração E2E.
* **Pontos Fortes:** Alto domínio de engenharia de redes e do AT Protocol; implementação resiliente do gerenciamento de sessões com cache local e respeito aos *rate limits*; capacidade de entrega veloz dos módulos essenciais do pipeline.
* **Desafio Superado:** Lidar com particularidades do SDK `atproto` no tratamento de registros concorrentes e contornar erros de concorrência entre o processo HTTP e o worker em segundo plano.

### 2.3 Dupla de Código B (Raissa & Samantha) — Inteligência Factual e Verificação
* **Escopo:** Camada de LLMs via LiteLLM, provedores de evidência (Wikipedia, Google Fact Check, RSS de agências com `pgvector`), *Chain-of-Verification* (CoVe), *Self-RAG*, *Multi-Agent Debate* e calibração estatística via *Conformal Risk Control* (CRC).
* **Pontos Fortes:** Raro equilíbrio entre rigor acadêmico e viabilidade prática de código; implementação de arquitetura de portas puras com *fakes*, permitindo que todos os testes unitários e de integração passassem com tempo de resposta quase instantâneo; preocupação exemplar com a prevenção de alucinações e fundamentação da abstenção algorítmica.
* **Desafio Superado:** Balanceamento dos tempos de inferência das rodadas de debate multiagente para manter o tempo total de verificação dentro de limites compatíveis com um serviço em tempo real.

---

## 3. Autoavaliação da Dupla de Documentação e Governança

Esta seção detalha a autoavaliação reflexiva da dupla responsável pela documentação técnica, governança de processos e preparação do showcase final do projeto (**Kyara Esteves de Sousa** e **Antonio Leonardo Souto Gomes**).

### 3.1 Contribuições Realizadas pela Dupla
A dupla assumiu a responsabilidade de manter **100% da documentação e governança do projeto viva, atualizada e integrada ao repositório via GitHub**, atuando como guardiã da coerência entre os requisitos teóricos do desafio e a engenharia de software implementada:

1. **Infraestrutura Documental e Automação:** Configuração e implantação do portal MkDocs com tema Material, hospedado via GitHub Actions no GitHub Pages, com checagem estrita de compilação integrada ao CI.
2. **Rastreabilidade Bidirecional dos Requisitos:** Construção e refinamento da matriz em `docs/requisitos.md`, conectando cada um dos 16 Requisitos Funcionais e 7 Não-Funcionais às suas respectivas *Guiding Questions* e issues no GitHub.
3. **Formalização das Matrizes de Decisão:** Documentação detalhada dos modelos operacionais de triagem e intervenção socrática em `docs/pesquisa/matrizes.md`, garantindo embasamento científico para a atuação do agente.
4. **Governança e Memória do Projeto:** Redação das atas formais de alinhamento metodológico e de arquitetura ([Ata 01](../atas/ata01.md) e [Ata 02](../atas/ata02.md)), bem como o acompanhamento contínuo dos [Checkpoints do MVP](../atas/checkpoints.md).
5. **Pesquisa e Referencial Teórico:** Sistematização aprofundada das [Guiding Questions](../pesquisa/guiding-questions.md), catalogação do levantamento de [Ideias e Fontes](../pesquisa/ideias-e-fontes.md) e compilação da [Bibliografia Acadêmica e Técnica](../referencias.md).

6. **Guias Práticos e Showcase:** Elaboração do [Guia de Uso Prático da Ferramenta](../guia-de-uso.md) e estruturação do material narrativo para a apresentação final.

---

### 3.2 Autoavaliação Individual: Kyara Esteves de Sousa

* **Papel no Projeto:** Pesquisadora teórica, redatora metodológica e analista de requisitos.
* **Autoavaliação Qualitativa:**
  > *"Minha atuação concentrou-se em garantir que a solução técnica construída pelas duplas de desenvolvimento mantivesse fidelidade incondicional aos princípios epistemológicos e éticos definidos no início do desafio. Dediquei-me à formulação profunda das Guiding Questions, à articulação teórica do método socrático como contraponto ao efeito backfire e à estruturação dos modelos de tomada de decisão.
  >
  > O maior desafio pessoal foi acompanhar o ritmo acelerado de commits e alterações de arquitetura realizados pelas duplas de código, exigindo leitura atenta dos Pull Requests e dos arquivos de domínio para que a documentação técnica não ficasse defasada em relação ao código real. Essa experiência reforçou a importância da rastreabilidade contínua e do trabalho verdadeiramente integrado em equipe multidisciplinar."*
* **Pontos de Destaque:**
  - Clareza e rigor conceitual na transposição de artigos científicos para requisitos acionáveis de software.
  - Construção do guia de uso amigável e inclusivo para o usuário final da rede Bluesky.
  - Excelência na escrita técnica e adesão rigorosa aos padrões do projeto.

---

### 3.3 Autoavaliação Individual: Antonio Leonardo Souto Gomes

* **Papel no Projeto:** Arquiteto documental, gestor de automações do MkDocs e redator de governança técnica.
* **Autoavaliação Qualitativa:**
  > *"Foquei meus esforços na estruturação técnica do ecossistema de documentação: garantia de deploy contínuo via GitHub Actions, organização da árvore de navegação do MkDocs, documentação sistemática das atas de reunião e acompanhamento dos marcos de entrega nos checkpoints.
  >
  > Trabalhar com a restrição de dez dias exigiu foco absoluto em síntese e padronização. Consegui estruturar os templates de ADRs e manter o registro histórico de decisões acessível para qualquer pessoa que consulte o repositório. O aprendizado em automatizar validações de integridade documental com o CI do GitHub foi um diferencial significativo na minha formação."*
* **Pontos de Destaque:**
  - Padronização estética e funcional do site do projeto com suporte a diagramas Mermaid e alertas visuais.
  - Registro fiel das discussões de arquitetura e decisões de projeto.
  - Colaboração fluida e complementar com a Kyara na divisão de tarefas da dupla.

---

## 4. Síntese de Maturidade e Aprendizagem Coletiva (CBL)

A trajetória da equipe ao longo do projeto ContrarIA evidenciou a eficácia da abordagem **Challenge-Based Learning**:

```
FASE ENGAGE                     FASE INVESTIGATE                   FASE ACT
(09/09 a 15/09)                 (16/09 a 19/09)                    (20/09 a 26/09)
───────────────                 ─────────────────                  ───────────────
Brainstorming aberto;           Estudo da literatura de CoVe,      Implementação modular em 3
debate sobre desinformação      Self-RAG, CRC e bots;              duplas paralelas; CI estrito;
e efeito backfire;              formulação das Guiding             deploy do Ozone e bot ativo
definição da Pergunta           Questions e da Matriz de           no Bluesky com verificação
Essencial e papéis.             Requisitos MoSCoW.                 socrática e auditável.
```

### Principais Lições Aprendidas pelo Time:
1. **O poder do contrato prévio:** Definir entidades e portas abstratas no dia zero eliminou 90% dos atritos típicos de integração entre desenvolvedores.
2. **A importância da abstenção formal:** Em inteligência artificial aplicada a temas sensíveis como política e eleições, saber **quando não responder** é tão importante quanto responder com precisão.
3. **Documentação como código (*Docs as Code*):** Tratar a documentação com o mesmo rigor de versionamento, revisão por pares e automação de testes do código fonte transforma a base de conhecimento em um ativo vivo e confiável do produto.

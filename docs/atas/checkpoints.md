# Checkpoints de Acompanhamento do MVP

Registro sistemático do progresso operacional, entregas das duplas e evolução do MVP ContrarIA ao longo da janela de execução (**17/09 a 26/09/2026**).

---

## Metodologia dos Checkpoints

Na ausência de sprints tradicionais de longa duração, a equipe realiza **checkpoints a cada 2 dias**. Cada checkpoint avalia:
1. **Entregas Concluídas**: Pull Requests revisados e mergeados na branch principal (`main`).
2. **Entregas em Andamento**: Pull Requests abertos e branches ativas.
3. **Bloqueios e Riscos**: Dependências atrasadas ou desvios de escopo.
4. **Alinhamento entre Trilhas**: Validação das interfaces entre as duplas.

---

## Checkpoint 1 – 18/09/2026 (Sexta-feira)

* **Marco temporal**: Início das trilhas paralelas de desenvolvimento após congelamento do setup.

### Status por Trilha

#### 1. Trilha A — Víctor Schmidt (Infraestrutura e Coleta)
- **Entregas**: PR [#35](https://github.com/moonshinerd/ContrarIA/pull/35) mergeado com sucesso (Setup inicial: repositório, ambiente Docker Compose, Makefile, CI e esqueleto do MkDocs).
- **Em andamento**: Início do desenvolvimento do cliente Bluesky na branch `feature/cliente-bluesky` (Issue [#10](https://github.com/moonshinerd/ContrarIA/issues/10)).
- **Bloqueios**: Nenhum.

#### 2. Raissa + Samantha (Verificação e IA)
- **Em andamento**: 
  - Estruturação do cliente de inferência multi-provedor na branch `feature/19-cliente-llm` (Issue [#19](https://github.com/moonshinerd/ContrarIA/issues/19)).
  - Modelagem dos provedores de evidência primários (Wikipedia e Google Fact Check) na branch `feature/20-fontes-evidencia` (Issue [#20](https://github.com/moonshinerd/ContrarIA/issues/20)).
- **Bloqueios**: Nenhum.

#### 3. Kyara + Antonio (Documentação e Governança)
- **Em andamento**: 
  - Configuração do workflow de deploy contínuo do MkDocs via GitHub Pages na branch `feature/mkdocs-pages` (Issue [#28](https://github.com/moonshinerd/ContrarIA/issues/28)).
- **Bloqueios**: Nenhum.

---

## Checkpoint 2 – 20/09 e 21/09/2026 (Fim de Semana / Segunda-feira)

* **Marco temporal**: Consolidação dos primeiros módulos funcionais e publicação da documentação técnica.

### Status por Trilha

#### 1. Trilha A — Víctor Schmidt (Infraestrutura, Coleta e Ações)
- **Entregas Concluídas**:
  - **PR [#36](https://github.com/moonshinerd/ContrarIA/pull/36) mergeado na `main`**: Conclusão da Issue [#10](https://github.com/moonshinerd/ContrarIA/issues/10) (Cliente Bluesky completo com sessão persistida, leituras públicas, busca autenticada e autolabeler).
- **Próximas Atividades**:
  - Início da coleta contínua de postagens via *Jetstream* (Issue [#11](https://github.com/moonshinerd/ContrarIA/issues/11)).
  - Desenvolvimento do módulo de cálculo heurístico de *Bot Score* (Issue [#13](https://github.com/moonshinerd/ContrarIA/issues/13)).
- **Bloqueios**: Nenhum.

#### 2. Raissa + Samantha (Verificação e Inteligência)
- **Entregas em Revisão (PRs Abertos)**:
  - **PR [#37](https://github.com/moonshinerd/ContrarIA/pull/37)**: Implementação das fontes Wikipedia e Google Fact Check com cache em memória (Issue [#20](https://github.com/moonshinerd/ContrarIA/issues/20)).
  - **PR [#39](https://github.com/moonshinerd/ContrarIA/pull/39)**: Provedores de busca web e acervo RSS com persistência pgvector (Issue [#21](https://github.com/moonshinerd/ContrarIA/issues/21)).
  - **PR [#40](https://github.com/moonshinerd/ContrarIA/pull/40)**: Cliente LLM multi-provedor baseado em LiteLLM (Issue [#19](https://github.com/moonshinerd/ContrarIA/issues/19)).
  - **PR [#41](https://github.com/moonshinerd/ContrarIA/pull/41)**: Pré-filtro clássico de desinformação com modelo supervisionado em PT-BR (Issue [#26](https://github.com/moonshinerd/ContrarIA/issues/26)).
- **Próximas Atividades**:
  - Iniciar a decomposição de alegações e o protocolo CoVe (Issue [#22](https://github.com/moonshinerd/ContrarIA/issues/22)).
- **Bloqueios**: Nenhum.

#### 3. Kyara + Antonio (Documentação e Governança)
- **Entregas Concluídas**:
  - **PR [#38](https://github.com/moonshinerd/ContrarIA/pull/38) mergeado na `main`**: Conclusão da Issue [#28](https://github.com/moonshinerd/ContrarIA/issues/28) (Workflow de deploy automatizado do site no GitHub Pages via GitHub Actions).
- **Entregas em Revisão (PRs Abertos)**:
  - **PR [#42](https://github.com/moonshinerd/ContrarIA/pull/42)**: Entrega da Matriz Completa de Requisitos (RF01–RF16 e RNF01–RNF07) com rastreabilidade formal e documentação das Matrizes de Decisão (Intervenção e Priorização) em `docs/pesquisa/matrizes.md`.
- **Próximas Atividades**:
  - Finalização da Ata 02 de Planejamento e publicação deste histórico de Checkpoints (Issue [#30](https://github.com/moonshinerd/ContrarIA/issues/30)).
  - Migração das *Guiding Questions* da pesquisa teórica (Kyara - Issue [#29](https://github.com/moonshinerd/ContrarIA/issues/29)).
  - Início da elaboração dos primeiros Registros de Decisão Arquitetural (ADRs - Issue [#31](https://github.com/moonshinerd/ContrarIA/issues/31)).
- **Bloqueios**: Nenhum.

---

## Checkpoint 3 – 22/09 e 23/09/2026 (Terça e Quarta-feira)

* **Marco temporal**: Conclusão da esteira central de IA de verificação, chegada da coleta massiva em tempo real via Jetstream e consolidação integral do portfólio de pesquisa e decisões arquiteturais.

### Status por Trilha

#### 1. Trilha A — Víctor Schmidt (Infraestrutura, Coleta e Ações)
- **Entregas Concluídas**:
  - **PR [#41](https://github.com/moonshinerd/ContrarIA/pull/41) mergeado na `main`**: Conclusão da Issue [#26](https://github.com/moonshinerd/ContrarIA/issues/26) (Pré-filtro clássico treinado em PT-BR para descarte rápido com custo zero de inferência).
  - **PR [#50](https://github.com/moonshinerd/ContrarIA/pull/50) mergeado na `main`**: Conclusão da Issue [#11](https://github.com/moonshinerd/ContrarIA/issues/11) (Coletor assíncrono em tempo real via WebSocket do *Jetstream* do Bluesky, com filtragem temática e snapshots de engajamento).
- **Próximas Atividades**:
  - Finalização da integração E2E do orquestrador do pipeline (Issue [#17](https://github.com/moonshinerd/ContrarIA/issues/17)), conectando a coleta e o bot score com o VerificationService.
  - Finalização dos módulos de *Bot Score* heurístico (Issue [#13](https://github.com/moonshinerd/ContrarIA/issues/13)) e intervenção socrática via *Quote Post* (Issue [#14](https://github.com/moonshinerd/ContrarIA/issues/14)).
- **Bloqueios**: Nenhum.

#### 2. Raissa + Samantha (Verificação, Raciocínio Epistêmico e Benchmarks)
- **Entregas Concluídas**:
  - **PR [#49](https://github.com/moonshinerd/ContrarIA/pull/49) mergeado na `main`**: Conclusão da Issue [#23](https://github.com/moonshinerd/ContrarIA/issues/23) (Implementação do *Self-RAG* com recuperação adaptativa de evidências e tokens de reflexão crítica para eliminação de alucinações).
  - **PR [#51](https://github.com/moonshinerd/ContrarIA/pull/51) mergeado na `main`**: Conclusão da Issue [#24](https://github.com/moonshinerd/ContrarIA/issues/24) (Debate Multiagente — MAD com Promotor, Defensor, Juiz epistêmico e cálculo da métrica de certeza P(IK)).
  - **PR [#52](https://github.com/moonshinerd/ContrarIA/pull/52) mergeado na `main`**: Conclusão da Issue [#25](https://github.com/moonshinerd/ContrarIA/issues/25) (Calibração estatística via *Conformal Risk Control* — CRC em runtime e `VerificationService`, garantindo abstenção formal com taxa de falsos positivos controlada a α ≤ 0,05).
- **Entregas em Revisão (PRs Abertos)**:
  - **PR [#54](https://github.com/moonshinerd/ContrarIA/pull/54)**: Conclusão da Issue [#27](https://github.com/moonshinerd/ContrarIA/issues/27) (Benchmark reproduzível de veredito com 150 ClaimReviews PT-BR, 17 cenários de ablação e medição de custo e latência).
- **Próximas Atividades**:
  - Suporte à amarração E2E na Issue [#17](https://github.com/moonshinerd/ContrarIA/issues/17).
- **Bloqueios**: Nenhum. Toda a trilha de inteligência de verificação entregue e testada no prazo previsto!

#### 3. Kyara + Antonio (Documentação, Governança e Decisões)
- **Entregas Concluídas**:
  - **PR [#42](https://github.com/moonshinerd/ContrarIA/pull/42) mergeado na `main`**: Especificação completa de Requisitos (RF01–RF16, RNF01–RNF07) com rastreabilidade formal e documentação das Matrizes de Decisão (Intervenção e Priorização) em `docs/pesquisa/matrizes.md`.
  - **PR [#43](https://github.com/moonshinerd/ContrarIA/pull/43) mergeado na `main`**: Publicação formal da Ata 02 de Planejamento do MVP e registro dos Checkpoints 1 e 2.
- **Entregas em Revisão (PRs Abertos e Aprovados)**:
  - **PR [#45](https://github.com/moonshinerd/ContrarIA/pull/45)**: Documentação detalhada da arquitetura do pipeline (`docs/arquitetura/pipeline.md`) e os 12 Registros de Decisão Arquitetural (`docs/adr/0001` a `0012`) (Antonio - Issue [#31](https://github.com/moonshinerd/ContrarIA/issues/31)).
  - **PR [#48](https://github.com/moonshinerd/ContrarIA/pull/48)**: Glossário Técnico formal com 18 conceitos-chave categorizados em 4 eixos temáticos (Antonio - Issue [#32](https://github.com/moonshinerd/ContrarIA/issues/32)).
  - **PR [#53](https://github.com/moonshinerd/ContrarIA/pull/53) (Aprovado por Antonio)**: Portfólio de pesquisa com as 7 Guiding Questions (GQ01–GQ07), levantamento de Ideias e Fontes, Metodologia Scrum e Papéis, Autoavaliações da equipe no modelo CBL, Referências Bibliográficas e Guia Prático de Uso (Kyara - Issue [#29](https://github.com/moonshinerd/ContrarIA/issues/29) e [#32](https://github.com/moonshinerd/ContrarIA/issues/32)).
- **Próximas Atividades**:
  - Merge dos PRs #45, #48 e #53 na `main`, fechando formalmente as tarefas [#29](https://github.com/moonshinerd/ContrarIA/issues/29) e [#31](https://github.com/moonshinerd/ContrarIA/issues/31).
  - Publicação dos resultados de benchmark de veredito no MkDocs (Issue [#33](https://github.com/moonshinerd/ContrarIA/issues/33)).
  - Estruturação do material do Showcase final e roteiro de demonstração (Issue [#34](https://github.com/moonshinerd/ContrarIA/issues/34)).
- **Bloqueios**: Nenhum.

---

## Síntese de Saúde do Projeto

| Indicador | Situação | Observações |
|---|---|---|
| **Aderência ao Cronograma** | 🟢 Verde (Excelente) | Todas as duplas cumpriram 100% de seus objetivos prévios à integração final. |
| **Contratos de Interface** | 🟢 Estável | Zero quebra de contratos de domínio; testes unitários das três trilhas executam sem fricção. |
| **Prontidão para Integração** | 🟢 Verde (Pronto para E2E) | Com a verificação (PR #52) e a coleta Jetstream (PR #50) mergeadas, a integração E2E ([#17](https://github.com/moonshinerd/ContrarIA/issues/17)) conta com todos os blocos prontos para o fechamento. |

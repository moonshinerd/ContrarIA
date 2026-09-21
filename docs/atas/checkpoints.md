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

## Checkpoint 1 – 18/09/2026 (Quinta-feira)

* **Marco temporal**: Início das trilhas paralelas de desenvolvimento após congelamento do setup.

### Status por Dupla

#### 1. Victor + Marlon (Infraestrutura e Coleta)
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

### Status por Dupla

#### 1. Victor + Marlon (Infraestrutura, Coleta e Ações)
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

## Síntese de Saúde do Projeto

| Indicador | Situação | Observações |
|---|---|---|
| **Aderência ao Cronograma** | 🟢 Verde (No prazo) | Todas as duplas estão entregando as tarefas da janela 17/09–21/09. |
| **Contratos de Interface** | 🟢 Estável | As entidades de `domain/entities.py` mantiveram-se consistentes. |
| **Prontidão para Integração** | 🟡 Monitorando | A integração E2E (Issue [#17](https://github.com/moonshinerd/ContrarIA/issues/17)) segue prevista para 24/09 conforme planejado. |

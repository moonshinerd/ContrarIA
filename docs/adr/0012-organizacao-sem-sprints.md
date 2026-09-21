# 0012 — Organização de Trabalho sem Sprints: Duplas Paralelas e Dependências Explícitas

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** docs/planejamento.md, Épico #7

## Contexto
Metodologias ágeis convencionais (como Scrum) estruturam o desenvolvimento em ciclos repetitivos chamados *Sprints*, usualmente de duas semanas cada, com reuniões dedicadas de planejamento de sprint, retrospectiva, refinamento e reuniões diárias (*dailies*).
No entanto, o projeto ContrarIA opera sob uma restrição temporal singular: **a janela total de desenvolvimento do MVP é de apenas 10 dias corridos (17/09 a 26/09/2026)**. Em 10 dias, é impossível rodar múltiplos ciclos iterativos de sprints sem que as cerimônias de processo consumam uma fração desproporcional do tempo útil de engenharia.

## Decisão
Abolir o conceito de sprints temporais e adotar um **modelo de engenharia concorrente baseado em três mecanismos complementares**:
1. **Três Duplas Paralelas Especializadas**:
   - Victor + Marlon: Infraestrutura, cliente Bluesky, coleta, bot score e intervenção.
   - Raissa + Samantha: Inteligência artificial, fontes de evidência, debate multiagente e benchmarks.
   - Kyara + Antonio: Governança, documentação no MkDocs, matrizes de decisão, atas e showcase.
2. **Desenvolvimento Orientado a Contratos (*Contract-First*)**:
   - As interfaces de dados fundamentais (`app/domain/entities.py`) e as portas abstratas (`LLMPort`, `EvidenceSource`, `TextClassifierPort`) foram padronizadas logo no setup inicial (#9). Cada dupla desenvolve seu código contra essas interfaces utilizando objetos simulados (*fakes*) nos testes unitários, sem precisar esperar o código real das outras duplas.
3. **Mapeamento de Dependências Reais no GitHub**:
   - Em vez de um backlog solto, o projeto utiliza a funcionalidade nativa *Blocked by* do GitHub Issues. Uma tarefa só se torna "Pronta" para desenvolvimento quando tudo o que a bloqueia é mergeado. A sincronização entre as trilhas é aferida por **Checkpoints a cada 2 dias**.

## Alternativas consideradas
- **Sprints Curtas de 2 Dias**: Descartadas pela sobrecarga e burocracia excessiva de planejar e encerrar sprints a cada 48 horas.
- **Desenvolvimento Livre sem Planejamento Prévio Fechado**: Descartado pelo altíssimo risco de retrabalho, incompatibilidade de contratos entre os módulos e bloqueios silenciosos entre os integrantes.

## Consequências
- **Positivas**:
  - Paralelismo máximo: as três duplas conseguem trabalhar simultaneamente desde o primeiro dia sem colisões.
  - Eficiência de tempo: zero tempo desperdiçado em reuniões cerimoniais improdutivas.
  - Previsibilidade: o caminho crítico para a entrega do MVP é visível por meio do gráfico de dependências do repositório.
- **Negativas / Riscos assumidos**:
  - Qualquer alteração não combinada nas entidades de contrato (`entities.py`) quebra o trabalho paralelo, exigindo comunicação imediata nos PRs entre as duplas.

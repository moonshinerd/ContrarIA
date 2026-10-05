# ContrarIA

<div style="display: flex; align-items: center; gap: 1.5rem; margin: 1rem 0 2rem 0; flex-wrap: wrap;">
  <img src="assets/logo.png" alt="Logo ContrarIA" style="width: 100px; height: 100px; object-fit: contain; border-radius: 50%; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);" />
  <div style="flex: 1; min-width: 260px;">
    <h3 style="margin: 0 0 0.5rem 0; font-size: 1.25rem;">Inteligência Coletiva Contra a Desinformação</h3>
    <p style="margin: 0; color: var(--md-default-fg-color--light);">
      Agente autônomo focado na detecção de bots e na mitigação de desinformação política no <strong>Bluesky</strong>. Projeto desenvolvido como parte do <em>Challenge Based Learning (CBL) - Challenge 1</em>.
    </p>
  </div>
</div>

> **Pergunta Essencial:** Como sistemas de inteligência artificial podem ajudar as pessoas a avaliar a confiabilidade de informações em tempo real sem substituir seu próprio pensamento crítico?

---

## Pilares do Sistema

<div class="grid cards" markdown>

-   :material-lightning-bolt:{ .lg .middle } __Coleta & Triagem em Tempo Real__

    ---

    Consumo ultrarrápido via WebSocket do Jetstream (Bluesky) com priorização por relevância e cálculo de bot score heurístico.

    [:octicons-arrow-right-24: Ver Pipeline](arquitetura/pipeline.md)

-   :material-scale-balance:{ .lg .middle } __Verificação Epistêmica Rigorosa__

    ---

    Verificação local Jev com fontes de evidência, classificação discriminativa Cross-Encoder NLI (mDeBERTa-v3) e
    calibração por Conformal Risk Control. O fluxo multiagente anterior segue
    disponível como alternativa experimental.

    [:octicons-arrow-right-24: Ver Decisões de Arquitetura (ADRs)](adr/index.md)

-   :material-shield-check:{ .lg .middle } __Intervenção Ética & Labeling__

    ---

    Intervenções públicas via Quote Posts neutros e acolhedores, além de rotulagem automatizada de contas maliciosas via Ozone Labeler.

    [:octicons-arrow-right-24: Ver Requisitos](requisitos.md)

-   :material-book-open-page-variant:{ .lg .middle } __Governança, Métricas & Vocabulário__

    ---

    Rastreabilidade MoSCoW, matrizes de decisão, atas deliberativas, checkpoints bienais/frequentes e glossário técnico completo.

    [:octicons-arrow-right-24: Ver Glossário Técnico](glossario.md)

</div>

---

## Estrutura da Documentação

- [:octicons-project-roadmap-24: **Planejamento**](planejamento.md) — Matriz de dependências, divisão de duplas operacionais e dinâmica de trabalho sem sprints.
- [:octicons-checklist-24: **Requisitos do Sistema**](requisitos.md) — Especificação completa de requisitos funcionais (RF01–RF16) e não-funcionais (RNF01–RNF07) com classificação MoSCoW.
- [:octicons-search-24: **Portfólio de Pesquisa**](pesquisa/guiding-questions.md) — As 7 perguntas norteadoras (GQ01–GQ07), [ideias e fontes](pesquisa/ideias-e-fontes.md) e [matrizes de decisão](pesquisa/matrizes.md).
- [:octicons-organization-24: **Processo & Governança**](processo/scrum.md) — Metodologia Scrum adaptada a duplas paralelas, governança ágil e dinâmicas de entrega conjunta.
- [:octicons-book-24: **Guia Prático de Uso**](guia-de-uso.md) — Manual para usuários no Bluesky, intervenção socrática e assinatura do Ozone Labeler.
- [:octicons-sliders-24: **Calibração do Jev**](calibracao-jev.md) — Procedimento formal de controle de risco conformal (CRC), determinação do limiar $\hat{\lambda}$ e calibração estatística do classificador local.
- [:octicons-cpu-24: **Arquitetura & Pipeline**](arquitetura/pipeline.md) — Diagrama de fluxo ponta a ponta e portas de integração desacopladas.
- [:octicons-file-badge-24: **Decisões Arquiteturais (ADRs)**](adr/index.md) — 13 registros de decisões cobrindo desde o ecossistema AT Protocol até o backend local Jev.
- [:octicons-graph-24: **Resultados e Benchmarks**](resultados/benchmark.md) — Avaliação experimental de acurácia, latência, custos vs. LLM, ablação de fontes e calibração estatística CRC.
- [:octicons-history-24: **Atas e Checkpoints**](atas/index.md) — Histórico de reuniões deliberativas e acompanhamento frequente de entregas.
- [:octicons-bookmark-24: **Glossário Técnico**](glossario.md) — Definições formais de termos e conceitos empregados no ecossistema ContrarIA.
- [:octicons-link-external-24: **Referências Bibliográficas**](referencias.md) — Acervo de artigos acadêmicos (arXiv, DOI, PMC) e documentações de protocolos.

---

## Equipe do Projeto

| Integrante | GitHub | Papel / Atribuição | Frente Operacional |
|:---|:---|:---|:---|
| **Víctor Hugo Lima Schmidt** | [@moonshinerd](https://github.com/moonshinerd) | Product Owner & Tech Lead | Trilha de Plataforma (Coleta, Triagem, Infra e E2E) |
| **Raissa Silva** | [@RaissaOliveira19](https://github.com/RaissaOliveira19) | Developer (IA & Verificação) | Trilha de Verificação Factual e IA (Self-RAG, CRC e Benchmark) |
| **Samantha Yumi Tanaka** | [@ySamantha](https://github.com/ySamantha) | Developer (IA & Verificação) | Trilha de Verificação Factual e IA (CoVe, MAD, Pré-filtro e Feeds) |
| **Kyara Esteves de Sousa** | [@Kyara2](https://github.com/Kyara2) | Developer (Pesquisa & Requisitos) | Trilha de Documentação e Governança (GQ01–GQ07, Requisitos e Matrizes) |
| **Antonio Leonardo Souto Gomes** | [@AntonioLeonardoUNB](https://github.com/AntonioLeonardoUNB) | Developer (Arquitetura & Processo) | Trilha de Documentação e Governança (Arquitetura, CI/CD, ADRs e Showcase) |

---

!!! tip "Documentação em Evolução Contínua"
    Esta base de conhecimento é versionada e mantida em sincronia contínua com a evolução do código-fonte e das diretrizes do projeto. Caso encontre inconsistências ou queira propor melhorias, consulte nosso repositório no [GitHub](https://github.com/moonshinerd/ContrarIA).

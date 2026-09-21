# Ata de Reunião – Planejamento e Arquitetura do MVP

* **Data:** 16 de setembro de 2026
* **Fase Metodológica (CBL):** Transição Semana 1 (*Investigate*) para Semana 2 (*Act / MVP*)
* **Tema / Objetivo:** Definição do Escopo Fechado, Arquitetura Técnica e Modelo de Governança do MVP ContrarIA
* **Participantes:**
  - Antonio Leonardo Souto Gomes
  - Kyara Esteves de Sousa
  - Marlon Martins Braga
  - Raissa Silva
  - Samantha Yumi Tanaka
  - Víctor Hugo Lima Schmidt

---

## 1. Contexto e Motivação do Planejamento

Com o encerramento da fase investigativa preliminar e a entrega das *Guiding Questions* e da Matriz de Requisitos (RF/RNF), a equipe reuniu-se para consolidar a viabilidade técnica e delimitar o escopo executável para o MVP.

Considerando a restrição temporal severa (janela de execução de **10 dias: 17/09 a 26/09/2026**), deliberou-se pela substituição do modelo tradicional de *Sprints* de 2 semanas por um modelo contínuo baseado em **3 duplas com trilhas paralelas e dependências explícitas no GitHub**.

---

## 2. Decisões Técnicas de Projeto

Nesta reunião, foram deliberadas e aprovadas as seguintes decisões de arquitetura e engenharia que balizam todo o desenvolvimento do MVP:

### 2.1 Plataforma Operacional: Bluesky (AT Protocol)
* **Decisão:** O agente operará exclusivamente na rede social **Bluesky**, utilizando o protocolo descentralizado AT Protocol (via API pública e *firehose* Jetstream).
* **Justificativa:** O X (antigo Twitter) impõe restrições severas de custo em sua API e limites estritos de taxa para projetos acadêmicos. O Bluesky oferece APIs abertas, ecossistema voltado para transparência e suporte nativo a serviços independentes de moderação.

### 2.2 Estratégia de Intervenção: *Quote Post* Não-Invasivo
* **Decisão:** A intervenção pública ocorrerá estritamente por meio de **Quote Post** (repostagem citando o conteúdo original no perfil do próprio bot).
* **Restrições deliberadas:** O bot **não responderá diretamente no fio de comentários** (*replies*) e **não marcará o autor original via menção (@)**.
* **Justificativa:** Essa escolha reduz drasticamente o risco de conflito com a diretriz comunitária de *opt-in*, previne o efeito *backfire* (confronto direto com usuários radicalizados) e foca a comunicação na audiência espectadora (*bystanders*).

### 2.3 Serviço de Rotulagem e Moderação Descentralizada: Servidor Ozone
* **Decisão:** O projeto fará o deploy de uma instância oficial do **Ozone** (ferramenta de moderação e emissão de rótulos do AT Protocol).
* **Infraestrutura:** VPS dedicada, gerenciada via Caddy como proxy reverso e proteção de rede via Cloudflare.
* **Justificativa:** Permite que o ContrarIA atue como um *Labeler* oficial elegível pelos usuários da rede, carimbando publicações ou contas desinformativas de forma transparente.

### 2.4 Camada de Modelos de Linguagem (LLM)
* **Decisão:** Padronização da interface através da biblioteca **LiteLLM** integrada ao **OpenRouter**, mantendo suporte a instâncias locais via **Ollama**.
* **Justificativa:** Evita o acoplamento proprietário (*vendor lock-in*), viabiliza fallback automático entre diferentes provedores (OpenAI, Anthropic, Google) e possibilita testes de desenvolvimento locais sem custo de API.

### 2.5 Provedores de Evidência e Fact-Checking
* **Decisão:** Adoção de uma cesta diversificada de fontes de consulta externa:
  - Google Fact Check Tools API (checagens consolidadas de agências).
  - Wikipedia API (contextualização enciclopédica).
  - DuckDuckGo / Tavily Search (busca factual na web em tempo real).
  - Feeds RSS automatizados de agências de fact-checking nacionais e dados oficiais do TSE.
* **Justificativa:** Reduz alucinações e garante atualidade (RNF02), combinando fontes curadas por humanos com busca rápida.

### 2.6 Classificação em Dois Níveis: Pré-filtro Clássico e *Bot Score*
* **Decisão:** A triagem será composta por:
  - **Pré-filtro clássico**: Modelo supervisionado leve treinado em datasets nacionais de fake news para descarte imediato de ruído.
  - **Bot Score**: Algoritmo heurístico ponderado que avalia frequência de postagem, intervalo entre publicações e razão seguidores/seguindo (RF02/RF12).

### 2.7 Pipeline de Verificação Multiagente
* **Decisão:** Implementação de uma arquitetura modular de verificação contendo:
  - Extração e decomposição de alegações factuais.
  - **CoVe (Chain of Verification)**: Geração de perguntas de validação e busca de contraprovas.
  - **Self-RAG**: Recuperação sob demanda com autocrítica da relevância das fontes.
  - **Debate Multiagente e CRC**: Dois agentes com papéis analíticos distintos chegam a um consenso para gerar o veredito final com nota de corte para abstenção.

### 2.8 Corte Consciente de Escopo: Frontend Web Fora do MVP
* **Decisão:** O desenvolvimento de uma interface web gráfica em React foi **formalmente postergado para a fase pós-MVP (Épico #8)**.
* **Justificativa:** O valor central do desafio concentra-se na inteligência algorítmica, na integridade da verificação e na atuação do agente autônomo na rede social. Todo o esforço de engenharia deve focar no backend, no worker e nos serviços de inferência.

---

## 3. Organização e Governança da Equipe

Para garantir independência e paralelismo, o time foi dividido em 3 duplas com contratos de interface claros:

| Dupla | Trilha de Atuação | Escopo de Entrega |
|---|---|---|
| **Victor + Marlon** | Infraestrutura, Coleta, Triagem e Intervenção | Docker, CI, deploy, cliente Bluesky, Jetstream, Bot score, Quote post, Labeler Ozone e integração E2E. |
| **Raissa + Samantha** | Verificação de Informações e Inteligência | Portas LLM, fontes de evidência, Self-RAG, CoVe, debate multiagente e benchmarks quantitativos. |
| **Kyara + Antonio** | Documentação, Governança e Showcase | Site MkDocs no GitHub Pages, migração da pesquisa, requisitos rastreáveis, matrizes de decisão, atas, ADRs e material da apresentação final. |

### Regras Operacionais Deliberadas
1. **Desenvolvimento Orientado a Contratos**: As portas de domínio (`entities.py`, `LLMPort`, `EvidenceSource`) foram congeladas no setup inicial; qualquer alteração de contrato exige alinhamento com as outras duplas.
2. **Revisão por Pares Obrigatória**: Nenhum código ou documento entra na branch `main` sem PR e aprovação da outra pessoa da dupla.
3. **Checkpoints a cada dois dias**: O progresso consolidado será aferido e documentado em atas de checkpoint.

---

## 4. Próximos Passos Imediatos

1. Finalizar o setup do repositório, contêineres Docker e esqueleto do MkDocs (Víctor).
2. Publicar o MkDocs no GitHub Pages e estruturar a navegação (Kyara + Antonio).
3. Iniciar a implementação do cliente Bluesky (Victor + Marlon) e do cliente LLM (Raissa + Samantha).

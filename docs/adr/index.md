# Registros de Decisão Arquitetural (ADRs)

Um **ADR** (*Architectural Decision Record*, ou **Registro de Decisão Arquitetural**) é um documento curto em formato texto que captura uma decisão arquitetural relevante tomada no projeto, juntamente com o seu contexto, as alternativas avaliadas e suas consequências.

O padrão foi popularizado por Michael Nygard (2011) e é amplamente utilizado na engenharia de software para garantir rastreabilidade histórica, permitindo que qualquer pessoa da equipe entenda **por que** uma escolha foi feita e **quais foram as concessões** (*trade-offs*) assumidas, evitando retrabalho e discussões repetidas sobre decisões já fundamentadas.

!!! info "Guia de Siglas Utilizadas no Projeto"
    Para facilitar a leitura técnica das decisões e requisitos, a tabela abaixo consolida as siglas e convenções adotadas:

    | Sigla | Significado em Inglês / Técnico | Descrição no Contexto do ContrarIA |
    |---|---|---|
    | **ADR** | *Architectural Decision Record* | Registro formal de uma decisão técnica estrutural |
    | **RF** | Requisito Funcional | Funcionalidade explícita que o sistema implementa |
    | **RNF** | Requisito Não Funcional | Critério de qualidade técnica (desempenho, segurança, custos, confiabilidade) |
    | **GQ** | *Guiding Question* (Pergunta Norteadora) | Pergunta investigativa que orienta as decisões de arquitetura e mitigação |
    | **MVP** | *Minimum Viable Product* | Versão de escopo essencial para validação do agente autônomo |
    | **NLI** | *Natural Language Inference* | Classificação semântica de premissa × hipótese (sustenta, contradiz ou neutro) |
    | **LLM** | *Large Language Model* | Modelo generativo na nuvem (usado estritamente para redação e crítica socrática) |
    | **CRC** | *Conformal Risk Control* | Teoria estatística de garantia de erro calibrada por limiares de confiança |
    | **PDS** | *Personal Data Server* | Servidor do AT Protocol onde ficam hospedados os dados e posts da conta |
    | **DID** | *Decentralized Identifier* | Identificador criptográfico descentralizado e permanente de uma conta no Bluesky |
    | **XRPC** | *Extensible Remote Procedure Call* | Protocolo HTTP/REST nativo do AT Protocol usado pelo Bluesky e Ozone |
    | **OIDC** | *OpenID Connect* | Autenticação federada por tokens temporários usada pelo GitHub Actions no deploy |

---

## Índice Completo de Decisões do MVP

| ADR | Decisão | Status | Data | Requisitos / Origem |
|---|---|---|---|---|
| [**0001**](0001-bluesky.md) | Adoção da Plataforma Bluesky (AT Protocol) em vez de X ou Instagram | `Aceita` | 16/09/2026 | RF01, RF07, RNF03, RNF07, GQ05 |
| [**0002**](0002-quote-post.md) | Intervenção por Quote Post em vez de Resposta no Fio ou Menção Direta | `Aceita` | 16/09/2026 | RF05, RF06, RF14, RNF03, RNF04, GQ01 |
| [**0003**](0003-labeler-ozone.md) | Uso do Servidor Oficial Ozone para Rotulagem Descentralizada | `Aceita` | 16/09/2026 | RF07, RNF03, RNF07, GQ07 |
| [**0004**](0004-litellm-openrouter.md) | Abstração de Provedores de LLM com LiteLLM, OpenRouter e Ollama | `Aceita` | 16/09/2026 | RNF05, Issue #19 |
| [**0005**](0005-multiplas-fontes-evidencia.md) | Cesta Diversificada de Fontes de Evidência com Adapters Desacoplados | `Aceita` | 16/09/2026 | RF11, RNF02, Issues #20, #21 |
| [**0006**](0006-bot-score-heuristico.md) | Detecção de Contas Automatizadas via Bot Score Heurístico Ponderado | `Aceita` | 16/09/2026 | RF02, RF12, RNF05, Issue #13 |
| [**0007**](0007-verificacao-cove-selfrag-mad-crc.md) | Verificação com CoVe, Self-RAG, Debate Multiagente e Conformal Risk Control | `Aceita` | 16/09/2026 | RF03, RF15, RF16, RNF01, Issues #22–#25 |
| [**0008**](0008-pre-filtro-classico.md) | Pré-filtro Clássico Supervisionado em Datasets PT-BR | `Substituída por 0015` | 16/09/2026 | RNF01, RNF05, Issue #26 |
| [**0009**](0009-coleta-hibrida-jetstream-searchposts.md) | Coleta Híbrida de Publicações via Jetstream e API searchPosts | `Aceita` | 16/09/2026 | RF01, RF08, RNF07, Issue #11 |
| [**0010**](0010-frontend-fora-do-mvp.md) | Postergação de Interface Web (Frontend React) para Pós-MVP | `Aceita` | 16/09/2026 | RF13, Épico #8 |
| [**0011**](0011-deploy-vps-caddy-cloudflare.md) | Infraestrutura de Deploy em VPS com Docker Compose, Caddy e Cloudflare | `Alterada por 0020` | 16/09/2026 | RNF03, RNF05, RNF07, Issue #15 |
| [**0012**](0012-organizacao-sem-sprints.md) | Organização de Trabalho sem Sprints: Duplas Paralelas e Dependências Explícitas | `Aceita` | 16/09/2026 | docs/planejamento.md, Épico #7 |
| [**0013**](0013-backend-local-jev.md) | Backend de Verificação Local Jev com CRC por Modelo | `Aceita` | 28/09/2026 | RF03, RNF01, RNF05, PR #57 |
| [**0014**](0014-busca-web-searxng-trafilatura.md) | Busca Web Self-Hosted com SearXNG e Extração via Trafilatura | `Aceita` | 30/09/2026 | RF11, RNF02, RNF05 |
| [**0015**](0015-pre-filtro-tfidf-nao-integrado.md) | Pré-filtro TF-IDF não integrado ao pipeline | `Aceita` | 05/10/2026 | RNF01, RNF05, GQ04 |
| [**0016**](0016-remocao-do-tavily.md) | Remoção do Tavily da busca web | `Aceita` | 05/10/2026 | RF11, RNF02, RNF05 |
| [**0017**](0017-rotulagem-de-contas-ao-vivo.md) | Rotulagem de contas com `provavel-bot` ao vivo | `Aceita` | 05/10/2026 | RF02, RF07, RNF01, GQ07 |
| [**0018**](0018-concorrencia-e-contrapressao-do-worker.md) | Análises simultâneas e teto de fila no worker | `Aceita` | 05/10/2026 | RNF05, RF08, RF10, GQ04 |
| [**0019**](0019-fonte-citada-pelo-post-e-entidade.md) | Fonte citada pelo post e checagem de entidade | `Aceita` | 05/10/2026 | RNF01, RF03, GQ03 |
| [**0020**](0020-acesso-vm-tunel-cloudflare.md) | Acesso à VM e deploy por túnel Cloudflare, sem porta de entrada | `Aceita` | 05/10/2026 | RNF03, RNF05, RNF07 |
| [**0021**](0021-resiliencia-das-fontes-de-evidencia.md) | Resiliência das fontes de evidência | `Aceita` | 05/10/2026 | RNF01, RNF05, RF11 |
| [**0022**](0022-janela-de-maturacao-e-critic-semantico.md) | Janela de maturação (3 h a 48 h) e critic semântico | `Aceita` | 07/10/2026 | RNF01, RF03, RF05, GQ03 |
| [**0023**](0023-outbox-de-rotulos-do-ozone.md) | Outbox de rótulos do Ozone com repetição | `Aceita` | 07/10/2026 | RF06, RF07, RNF05, RNF06 |

---

## Revisão e Homologação Técnica

Em conformidade com a [Issue #31](https://github.com/moonshinerd/ContrarIA/issues/31), os 13 registros de decisões arquiteturais foram formalmente submetidos à revisão técnica paritária pelas duplas de desenvolvimento antes da fusão definitiva na branch principal (`main`):

* **ADRs 0001 a 0012:** Revisados e aprovados formalmente por Raissa Silva e Víctor Schmidt no [PR #45](https://github.com/moonshinerd/ContrarIA/pull/45).
* **ADR 0013:** Revisado e integrado no [PR #57](https://github.com/moonshinerd/ContrarIA/pull/57), acompanhado da rotina de calibração formal do backend local Jev.

## Template Padrão de ADR

Cada registro segue a estrutura padronizada abaixo (inspirada no modelo Michael Nygard e no padrão de engenharia do repositório):

```markdown
# NNNN — Título da Decisão

- **Status:** Proposta | Aceita | Substituída por NNNN
- **Data:** DD/MM/AAAA
- **Requisitos / GQs:** RF.., GQ..

## Contexto
O problema técnico, restrições e motivações.

## Decisão
A solução de engenharia adotada.

## Alternativas consideradas
Quais opções foram analisadas e por que foram rejeitadas.

## Consequências
Impactos positivos, novas dificuldades operacionais e riscos assumidos.
```

# Registros de Decisão Arquitetural (ADRs)

Registro formal das decisões técnicas de engenharia e arquitetura do projeto **ContrarIA**, documentando o contexto, alternativas descartadas e consequências de cada escolha.

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
| [**0008**](0008-pre-filtro-classico.md) | Pré-filtro Clássico Supervisionado em Datasets PT-BR | `Aceita` | 16/09/2026 | RNF01, RNF05, Issue #26 |
| [**0009**](0009-coleta-hibrida-jetstream-searchposts.md) | Coleta Híbrida de Publicações via Jetstream e API searchPosts | `Aceita` | 16/09/2026 | RF01, RF08, RNF07, Issue #11 |
| [**0010**](0010-frontend-fora-do-mvp.md) | Postergação de Interface Web (Frontend React) para Pós-MVP | `Aceita` | 16/09/2026 | RF13, Épico #8 |
| [**0011**](0011-deploy-vps-caddy-cloudflare.md) | Infraestrutura de Deploy em VPS com Docker Compose, Caddy e Cloudflare | `Aceita` | 16/09/2026 | RNF03, RNF05, RNF07, Issue #15 |
| [**0012**](0012-organizacao-sem-sprints.md) | Organização de Trabalho sem Sprints: Duplas Paralelas e Dependências Explícitas | `Aceita` | 16/09/2026 | docs/planejamento.md, Épico #7 |
| [**0013**](0013-backend-local-jev.md) | Backend de Verificação Local Jev com CRC por Modelo | `Aceita` | 28/09/2026 | RF03, RNF01, RNF05, PR #57 |

---

## Revisão exigida para conclusão

A [issue #31](https://github.com/moonshinerd/ContrarIA/issues/31) exige que cada um dos 12 ADRs seja revisado por alguém de uma dupla de código (Victor/Marlon ou Raissa/Samantha). O status `Aceita` registra a decisão arquitetural e não substitui essa revisão.

A revisão dos ADRs 0001 a 0012 está **pendente de registro no PR #45**. O ADR
0013 deve ser revisado junto ao PR #57. A pessoa revisora deve indicar
explicitamente quais ADRs revisou. A issue só deve ser considerada concluída
após essa revisão e a publicação dos documentos.

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

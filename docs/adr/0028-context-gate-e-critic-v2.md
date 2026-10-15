# 0028 — Context Gate, Critic V2 e Tipologia de Intervenção

- **Status:** Aceita
- **Data:** 15/10/2026
- **Requisitos / GQs:** RF05, RF06, RNF01, GQ01, GQ03, GQ04

## Contexto

Em 14 e 15 de outubro de 2026, com o início da operação do `ClaimHarvester` ([ADR 0027](0027-coletor-de-alegacoes-checadas.md)) e a remoção do piso de seguidores ([ADR 0024](0024-remove-piso-de-seguidores-e-faixa-de-silencio.md)), o `@contraria-bot.bsky.social` realizou 8 intervenções em produção. A auditoria direta na base de dados (`decisions` e `interventions`) e nos logs de execução revelou cinco falhas sistêmicas interligadas:

1. **Bug Estrutural no `ClaimHarvester`:** O construtor do veredito (`_verdict()`) preenchia `verdict.claim = candidate.post.text[:300]`. Ao chegar em `_is_claim_relevant_to_post(verdict.claim, post.text)`, a função comparava o post consigo mesmo, tornando a validação inócua. A alegação checada pela agência (`candidate.checked`) ficava restrita a um JSON auxiliar em `agent_outputs` e nunca era confrontada contra o texto do post.
2. **Critic Semântico Fail-Open:** Se o LLM falhasse, sofresse timeout ou respondesse fora do formato esperado (sem conter explicitamente a palavra `REPROVADA`), o código retornava `True, "Auditoria semântica indisponível"`, aprovando publicações em produção sob falha técnica.
3. **Cegueira e Descarte de Contexto:** O `BlueskyClient.get_thread_context()` percorria ancestrais e respostas, mas ignorava o embed de post citado (`thread.post.embed`). Além disso, o contexto recuperado ficava restrito ao snapshot do banco e à verificação factual do Jev, não sendo injetado nem no redator do quote post nem no Critic Semântico.
4. **Desconexão de Matérias Compartilhadas:** Quando um usuário publicava um link externo (ex.: matéria religiosa ou portal regional), o pipeline confrontava apenas o texto curto da postagem contra checagens externas não relacionadas (ex.: Polymarket ou manipulação de fotos), sem ler a matéria compartilhada no link do autor.
5. **Ausência de Tipologia de Intervenção e Sensibilidade a Atos de Fala:** O sistema tratava qualquer sinal adverso com o mesmo modelo socrático direto, sem distinguir humor/sátira/meme (ex.: risadas expressas como "KKKK"), desabafos genéricos sem alegação factual e perguntas contextuais legítimas sobre eventos onde houve desinformação.

## Decisão

Adotou-se uma arquitetura de proteção em profundidade centrada no princípio **Fail-Closed**:

1. **Correção Estrutural no `ClaimHarvester` (`app/jobs/claim_harvester.py`):**
   - `verdict.claim` passa a receber obrigatoriamente a alegação factual checada pela agência (`candidate.checked`).
   - O filtro de pertinência `_is_claim_relevant_to_post` exige ancoramento de termos informativos nucleares (mínimo de 2 tokens para alegações com 3+ palavras informativas).

2. **Entidade de Contexto Unificada (`PostContextBundle`):**
   - Modela integralmente o alvo da intervenção: texto do post, histórico do fio (`thread_context`), post citado via embed (`quoted_post_text` e autor) e resumo textual de links compartilhados (`shared_link_text`, hidratado via `fetch_article_text`).
   - O contexto completo é propagado para o gerador de quote posts (`quote_post_v2.txt`), para a verificação de grounding de entidades (`_find_hallucinated_entity`) e para o auditor semântico.

3. **Extração de Posts Citados no Bluesky (`BlueskyClient`):**
   - O método `get_thread_context()` inspeciona `thread.post.embed` (suportando `app.bsky.embed.record#view` e `recordWithMedia#view`) e inclui o post citado com prefixo `post citado: @autor: texto`.

4. **Critic V2 Estritamente Fail-Closed (`app/services/intervention.py` e `prompts/semantic_critic_v2.txt`):**
   - Publicação autorizada unicamente se a linha de decisão contiver explicitamente `DECISAO: APROVADA` (e não contiver `REPROVADA`).
   - Qualquer resposta malformada, incompleta, timeout de rede ou exceção de API resulta em abstenção imediata (`return False, reason`).
   - Avaliação explícita de atos de fala: posts identificados como sátira, piada, meme, risada ("KKKK") ou desabafo genérico são vetados com `DECISAO: REPROVADA`.
   - Veto obrigatório a associações não comprovadas (*Unsupported Association*), nas quais a checagem aborda números ou temas ausentes do post.

5. **Eliminação de Fallback Silencioso de Fontes:**
   - Em `_parse_agent_output()`, a ausência de linha `FONTE:` válida aborta a publicação imediatamente (`return "", []`), sem fallback artificial para a primeira fonte da lista.

## Tipologia de Intervenção

| Tipo | Condição | Ação |
| :--- | :--- | :--- |
| **`DIRECT_FACT_CHECK`** | Post afirma expressamente fato desmentido por checagem da agência. | Intervenção socrática pontual aprovada. |
| **`CONTEXTUAL_FACT_CHECK`** | Post noticia evento real onde circularam imagens de IA ou mídias manipuladas. | Pergunta socrática contextual sem acusação direta de má-fé permitida. |
| **`UNSUPPORTED_ASSOCIATION`** | Post trata de evento correlato mas não cita números ou entidades da checagem. | **ABSTAIN** obrigatório. |
| **`SPEECH_ACT_HUMOR`** | Meme, piada, desabafo ou risada expressa ("KKKK"). | **ABSTAIN** obrigatório. |

## Consequências

- **Positivas:** Intervenções públicas errôneas em posts humorísticos, desabafos ou matérias desconexas são bloqueadas na raiz. O bot passa a operar sob garantia fail-closed.
- **Observabilidade:** Toda rejeição pelo Critic Semântico ou por falta de pertinência é registrada nos logs e na justificativa da decisão, facilitando a auditoria contínua.
- **Garantia de Regressão:** Criada a suíte `tests/test_regression_adr0028.py` cobrindo exatamente os 5 casos reais identificados na auditoria técnica de produção.

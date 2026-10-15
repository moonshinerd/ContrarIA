# 0028 — Context Gate, Critic V2 e Tipologia de Intervenção

- **Status:** Aceita
- **Data:** 15/10/2026
- **Requisitos / GQs:** RF05, RF06, RNF01, GQ01, GQ03, GQ04

## Contexto

Em 14 e 15 de outubro de 2026, com o início da operação do `ClaimHarvester` ([ADR 0027](0027-coletor-de-alegacoes-checadas.md)) e a remoção do piso de seguidores ([ADR 0024](0024-remove-piso-de-seguidores-e-faixa-de-silencio.md)), o `@contraria-bot.bsky.social` realizou intervenções em produção que evidenciaram brechas no pipeline de moderação fática:

1. **Bug Estrutural no `ClaimHarvester`:** O construtor do veredito (`_verdict()`) preenchia `verdict.claim = candidate.post.text[:300]`. Ao chegar em `_is_claim_relevant_to_post(verdict.claim, post.text)`, a função comparava o post consigo mesmo, tornando a validação inócua. A alegação checada pela agência (`candidate.checked`) ficava restrita a um JSON auxiliar em `agent_outputs` e nunca era confrontada contra o texto do post.
2. **Critic Semântico Fail-Open:** Se o LLM falhasse, sofresse timeout ou respondesse fora do formato esperado (sem conter explicitamente a palavra `REPROVADA`), o código retornava `True, "Auditoria semântica indisponível"`, aprovando publicações em produção sob falha técnica.
3. **Cegueira e Descarte de Contexto:** O `BlueskyClient.get_thread_context()` percorria ancestrais e respostas, mas ignorava o embed de post citado (`thread.post.embed`). Além disso, o contexto recuperado ficava restrito ao snapshot do banco e à verificação factual do Jev, não sendo injetado nem no redator do quote post nem no Critic Semântico.
4. **Desconexão de Matérias Compartilhadas:** Quando um usuário publicava um link externo (ex.: matéria de imprensa, evento religioso ou portal regional), o pipeline confrontava apenas o texto curto da postagem contra checagens externas não relacionadas (ex.: Polymarket ou manipulação de fotos), sem ler a matéria compartilhada no link do autor.
5. **Brecha Contextual por Co-ocorrência de Evento (`CONTEXTUAL_FACT_CHECK`):** Uma formulação permissiva inicial permitia ao bot fazer perguntas sobre imagens manipuladas por inteligência artificial em posts que apenas noticiavam um evento real (ex.: manifestação em Copacabana), mesmo que o autor não tivesse compartilhado nem afirmado a imagem falsa desmentida.
6. **Vulnerabilidade no Parser por Substring:** O parser original buscava a substring `"APROVADA"` na linha de decisão, o que criava a brecha de interpretar respostas negativas como `DECISAO: NAO APROVADA` ou `DECISAO: DESAPROVADA` como se fossem aprovações válidas.
7. **Ausência de Tipologia de Intervenção e Sensibilidade a Metáforas e Atos de Fala:** O sistema tratava qualquer sobreposição de palavras com intervenção direta, sem distinguir humor/sátira/meme (ex.: risadas expressas como "KKKK"), metáforas/linguagem figurada (ex.: "colocou a tornozeleira eletrônica no bolso") e desabafos genéricos sem alegação factual.

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

4. **Fechamento da Brecha Contextual e Alinhamento de Contradição Fática:**
   - O prompt `quote_post_v2.txt` e o `semantic_critic_v2.txt` foram rigorosamente harmonizados: a intervenção exige **CONTRADIÇÃO FÁTICA POSITIVA**.
   - Para checagens sobre imagens adulteradas, vídeos manipulados ou fotos antigas descontextualizadas, a intervenção só é permitida se o post **efetivamente compartilhou ou afirmou a mídia falsa**. A simples menção de um evento verídico onde circularam desinformações não autoriza intervenção e classifica-se obrigatoriamente como `UNSUPPORTED_ASSOCIATION`.

5. **Critic V2 Estritamente Fail-Closed com Parser por Token Exato:**
   - Em `_validate_semantic_coherence` (`app/services/intervention.py`), o parser localiza a linha `DECISAO:`, remove o prefixo e extrai o token exato: a aprovação só ocorre se `decision_token == "APROVADA"`. Expressões como `NAO APROVADA`, `NÃO APROVADA`, `DESAPROVADA` ou `REPROVADA` são categoricamente rejeitadas.
   - Qualquer resposta malformada, incompleta, timeout de rede ou exceção de API resulta em abstenção imediata (*fail-closed*, `return False, reason`).
   - Avaliação explícita de atos de fala: posts identificados como sátira, meme, risada ("KKKK"), desabafo genérico ou uso metafórico/figurado de termos fáticos são vetados com `DECISAO: REPROVADA`.

6. **Eliminação de Fallback Silencioso de Fontes:**
   - Em `_parse_agent_output()`, a ausência de linha `FONTE:` válida aborta a publicação imediatamente (`return "", []`), sem fallback artificial para a primeira fonte da lista.

## Tipologia de Intervenção

| Tipo | Condição | Ação | Justificativa |
| :--- | :--- | :--- | :--- |
| **`DIRECT_FACT_CHECK`** | Post afirma expressamente fato desmentido por checagem da agência. | **INTERVENE** | Contradição fática direta com link da checagem. |
| **`CONTEXTUAL_FACT_CHECK`** | Post compartilhou ou endossou mídia desmentida (imagem/vídeo de IA ou montagem) ou distorção em quote embed. | **INTERVENE** | Pergunta contextual socrática focada na mídia compartilhada, sem acusação de má-fé. |
| **`UNSUPPORTED_ASSOCIATION`** | Post noticia evento real sem compartilhar a mídia falsa, ou a checagem aborda números e temas ausentes no post. | **ABSTAIN** | **Veto obrigatório:** Co-ocorrência temática de evento não justifica imputar boato ao autor. |
| **`SPEECH_ACT_HUMOR`** | Meme, piada, sátira, desabafo ou risada expressa ("KKKK"). | **ABSTAIN** | **Veto obrigatório:** Robô não intervém em humor ou desabafos coloquiais. |
| **`SPEECH_ACT_METAPHOR`** | Uso metafórico ou linguagem figurada de termo fático (ex.: "tornozeleira no bolso"). | **ABSTAIN** | **Veto obrigatório:** Não há intenção de afirmação fática literal. |

## Consequências

- **Positivas:** Intervenções públicas indevidas em posts que apenas noticiam eventos reais, matérias legítimas de imprensa, desabafos, piadas e metáforas são bloqueadas com 100% de rigor. O bot atua sob garantia estrita *fail-closed*.
- **Observabilidade:** Toda rejeição pelo Critic Semântico, por falta de pertinência ou por ato de fala/associação desconexa é registrada em `decisions` com o motivo estruturado, permitindo auditoria contínua e sem perda de histórico.
- **Garantia de Regressão:** Suíte robusta `tests/test_regression_adr0028.py` com 12 testes cobrindo todos os cenários reais auditados em produção (Mirella Tigrinho, Temer IPVA, Netasgard evangélico, Copacabana sem foto de IA, Copacabana com foto de IA, Alexandre Oliva tornozeleira de bolso, BrunoAntifa Copacabana Palace, G1 TSE, Paulo Pimenta Mídia NINJA, Dilma Resistente Brasil 247, fail-closed por indisponibilidade e testes do parser estrito).

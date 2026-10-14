# 0025 — Veredito adverso só com checagem que casa com a alegação

- **Status:** Item 1 revertido pelo [ADR 0026](0026-reverte-exigencia-de-casamento.md); demais itens mantidos (altera o [ADR 0024](0024-remove-piso-de-seguidores-e-faixa-de-silencio.md) no que diz respeito à fonte do veredito adverso)
- **Data:** 14/10/2026
- **Requisitos / GQs:** RF05, RF06, RNF01, GQ01

## Contexto
A análise de todas as 7.009 decisões de produção (05 a 14/10/2026) mostrou que o veredito adverso não era confiável:

- Só 59 decisões foram `false` ou `misleading` (0,8%). Quase todas vinham de uma página da Wikipédia, do link do próprio
  post (uma manchete verdadeira) ou de uma checagem do Google Fact Check sobre **outro** fato do mesmo tema (por exemplo,
  um post sobre cortes em Educação e Saúde recebeu a checagem "Flávio não anunciou o fim da Farmácia Popular").
- Os 4 quote posts publicados em 06/10 (`intervention_dry_run=false` em produção) foram sobre posts que não eram fake
  news.
- Casar por similaridade de embedding ou só por NLI contra a lista de checagens também falhou: dos 609 trechos de posts
  recentes, os pares "mesmo tema" eram muitos e os pares "mesma alegação" praticamente não existiam. Com um gate frouxo
  (nome em comum + NLI), os 4 casamentos achados eram falsos positivos ("LULA 13: promoveu avanços…" casando com "Lula
  jogou a bandeira no chão").
- A busca ativa por checagens trouxe só 34 de 7.989 posts: usava o título inteiro como consulta, e o `searchPosts` exige
  todos os termos. Nas buscas reais, o que aparece quando se procura a alegação checada são, sobretudo, os próprios posts de
  desmentido ("É falso que…", "VOTO SEM FAKE").

## Decisão
1. **Veredito adverso exige casamento com uma checagem.** `false` e `misleading` só saem quando o post repete a alegação
   que uma agência marcou como falsa ou enganosa. A leitura genérica da evidência (Wikipédia, imprensa, link citado) deixou
   de poder acusar: nesse caso o resultado é `insufficient_evidence`.
2. **Casamento com precisão (`_match_checked_claim`):** a alegação checada vem do `claim.text` do Google Fact Check, com a
   nota crua da agência, ou de títulos "É falso que X" do acervo RSS. O post precisa (a) compartilhar ao menos 2 termos
   informativos e um nome, sigla ou número da alegação, (b) cobrir pelo menos metade do conteúdo da alegação (por radical)
   e (c) ter entailment NLI ≥ 0,7 (post → alegação checada). A nota da agência define o rótulo e o entailment, a
   confiança. A calibração CRC continua valendo.
3. **Posts que já desmentem não casam** ("É falso que…", "boato", "VOTO SEM FAKE"): eles citam a alegação sem afirmá-la.
4. **Margem de 0,1** entre "factual" e "opinião" na triagem, e **linhas quebradas** passam a ser unidas quando a seguinte
   começa com negação, conectivo ou minúscula (o post #4618 perdia o "NÃO").
5. **Busca ativa:** a consulta passa a ser os termos específicos da alegação (nomes, siglas, números e as palavras mais
   longas, até 4), em vez do título. `FACTCHECK_SEARCH_MAX_ARTICLES` sobe de 8 para 30 e `FACTCHECK_SEARCH_MAX_QUERIES` de
   16 para 40. O acervo RSS (`rss_checkers`) passa a ser consultado pelo Jev junto com o Google Fact Check.

## Consequências
- O número de intervenções cai para perto de zero no curto prazo: nas 609 alegações avaliadas offline, nenhum post
  repetia uma alegação checada. É o preço de só acusar com checagem; antes, as acusações eram falsas.
- O volume futuro depende de oferta: mais fontes de checagem e buscas que tragam posts que **repetem** (e não desmentem)
  as alegações. As consultas por termos específicos e o `FACTCHECK_SEARCH_PRIORITY_BONUS` atuam nisso.
- Alternativa não implementada: responder com *contexto* ("agências checaram alegações parecidas: …") quando o tema casa,
  mas a alegação não. Daria volume, mas muda o papel do bot (não afirma que o post é falso) e exige decisão de produto.
- Para voltar ao comportamento anterior, não há flag: seria preciso reverter a regra de `_verify_claim`.

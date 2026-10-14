# 0026 — Reversão da exigência de casamento com a checagem

- **Status:** Aceita (reverte o item 1 do [ADR 0025](0025-veredito-adverso-so-com-checagem-casada.md))
- **Data:** 14/10/2026
- **Requisitos / GQs:** RF05, RF06, GQ01

## Contexto
O ADR 0025 passou a exigir que o post repetisse uma alegação já checada para qualquer veredito adverso. Isso derrubou
a chance de o bot publicar para perto de zero (nenhum post de 609 repetia uma alegação checada), e o objetivo do projeto é
aumentar a chance de intervenção.

## Decisão
- **Revertido:** a exigência de casamento. O veredito adverso volta à regra do [ADR 0024](0024-remove-piso-de-seguidores-e-faixa-de-silencio.md):
  precisa de ao menos uma fonte de checagem, imprensa ou oficial entre as evidências relevantes; só Wikipédia ou o link do
  próprio post abstém.
- **Mantido (aditivo):** o casamento com checagem como caminho extra para acusar, o filtro de posts que já desmentem, a
  busca ativa por termos específicos da alegação (30 artigos, 40 consultas), o acervo RSS como fonte do Jev, a junção de
  linhas quebradas e a margem de 0,1 entre "factual" e "opinião".

## Consequências
- Mais posts chegam a veredito adverso do que com o ADR 0025.
- Risco aceito: um veredito adverso pode vir de uma checagem sobre **outro fato do mesmo tema**. Na análise de 05 a 14/10,
  das 15 decisões adversas com checagem do Google, quase nenhuma tratava da mesma alegação do post.
- Em produção `INTERVENTION_DRY_RUN=false`: o que passar nessa regra é publicado. Para revisar antes de publicar, ligue
  `INTERVENTION_DRY_RUN=true`.

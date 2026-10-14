# 0027 — Coletor de alegações checadas

- **Status:** Aceita
- **Data:** 14/10/2026
- **Requisitos / GQs:** RF01, RF05, RF06, GQ01, GQ04

## Contexto
De 06 a 14/10/2026 o bot não publicou nada. O fluxo normal parte de posts políticos populares (palavras-chave e
`searchPosts` ordenado por engajamento) e procura checagem para eles; das 7.009 decisões de produção, só 59 foram
adversas e quase todas sem relação com a checagem encontrada. A busca guiada por checagens trouxe 34 de 7.989 posts,
porque usava o título inteiro da checagem como consulta e o `searchPosts` exige todos os termos.

Investigação com dados reais (291 checagens do Google Fact Check em 30 dias, 974 posts do Bluesky, 154 pares rotulados
à mão):

- Há posts no Bluesky repetindo alegações já checadas como falsas (Gilmar "vota usando celular na cabine", "Lula é o pai
  do Tigrinho", Flávio "quer tirar Nossa Senhora Aparecida do posto de padroeira", "o TSE mudou o local de votação de
  milhares de moradores", citações inventadas). Muitos são respostas em threads, com pouco engajamento: o fluxo atual
  não chega neles.
- O NLI local (mDeBERTa) não distingue "repete a alegação" de "fala do mesmo tema": precisão de ~12% com entailment ≥ 0,5.
- Qwen3 local como juiz (logprob de Sim/Não, sem gerar texto): 1,7B ≈ acaso (AUC 0,53); 4B com exemplos no prompt AUC
  0,86, precisão de 30 a 50%. Exigiria ~2,5 GB de RAM e o llama.cpp de volta na VM (4 vCPU, 9,7 GB, sem GPU) para um
  filtro ainda impreciso. Descartado.

## Decisão
Um job do worker (`app/jobs/claim_harvester.py`) inverte o funil, a cada `CLAIM_HARVEST_MINUTES`:

1. Pega as alegações falsas ou enganosas checadas nos últimos 30 dias: Google Fact Check (consultas amplas em
   `CLAIM_HARVEST_QUERIES`) e títulos "É falso que X" do acervo RSS.
2. Para cada uma, busca no Bluesky (`latest` e `top`, últimos 7 dias) os **dois termos mais raros** da alegação no corpus
   de posts (IDF), números incluídos. Nomes comuns ("Lula", "Flávio") não servem de consulta.
3. Filtros baratos: descarta desmentidos ("É falso que", "❌", link para a checagem, "NO AR."), exige cobertura da alegação
   ponderada por IDF ≥ 0,5, descarta quem contradiz a alegação (NLI do Jev, contradição ≥ 0,5), no máximo 3 posts por
   alegação e texto repetido entra uma vez.
4. Os candidatos ficam num backlog (24 h) e saem **um por rodada** de intervenção, quando a fila está vazia: a fila só
   publica o melhor de cada rodada.
5. O candidato entra no pipeline com veredito `false`/`misleading` (a nota da agência) e a checagem como fonte, marcado
   com `claim_harvest`. O piso de confiança 0,8 do Jev não se aplica: quem decide é a revisão das fontes e o auditor
   semântico (LLM), que leem a checagem e vetam quando o post não repete a alegação.

## Resultados do teste offline (sem LLM)
- Janela de 21 dias: 81 candidatos (~4/dia), dos quais ~15 repetem de fato a alegação (~20%); recuperou 7 dos 14
  positivos rotulados. Esperado: ~0,7 resposta correta por dia, se o auditor aprovar os verdadeiros e vetar o resto.
- Custo de LLM: ~4 candidatos/dia × ~US$ 0,0025 (gpt-6-luna) ≈ US$ 0,01/dia.

## Consequências
- O bot passa a ter um canal que chega a respostas de threads e posts de pouco alcance que repetem desinformação checada.
- A precisão antes do LLM é baixa (~20%): a qualidade final depende do auditor semântico. Acompanhe os vetos e as
  respostas publicadas nas primeiras semanas.
- O volume é limitado pelo que as agências checam: poucas respostas por dia, não dezenas.
- Para desligar: `CLAIM_HARVEST_ENABLED=false`.

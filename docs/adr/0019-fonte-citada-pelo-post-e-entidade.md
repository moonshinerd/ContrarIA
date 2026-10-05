# 0019 — Fonte citada pelo post e checagem de entidade

- **Status:** Aceita
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF01, RF03, GQ03

## Contexto
Em 05/10/2026 o bot publicou um quote post errado sobre um post de uma conta que republica manchetes do G1
("Resultado das eleições 2026 em Itacoatiara (AM): votação para presidente no E. M. Dom Pedro I, na 3ª zona eleitoral").
Ele afirmava que a reportagem situava a escola na 48ª zona eleitoral (Maribondo/AL). Existem duas escolas com o mesmo
nome em estados diferentes: o post estava correto, e o link dele apontava para a matéria certa. O post foi apagado.

Reproduzindo o caso localmente, o veredito foi `false` com 94%. As causas, todas confirmadas no código:

1. **Divisão de frases.** O divisor cortava depois de "E." (de "E. M."), e a alegação virou "Dom Pedro I, na 3ª zona
   eleitoral", sem a cidade. Esse fragmento casa com qualquer escola homônima.
2. **A fonte do próprio post não entrava como evidência.** O link do card nunca era lido.
3. **Evidência de outra entidade era aceita.** Uma página sobre a escola de Maribondo/AL (48ª zona) passou pelos filtros
   e o classificador a tratou como desmentido.

## Decisão
1. **Divisor de frases** (`_SENTENCE_SPLIT`) não corta depois de sigla de uma letra (`E. M.`) nem de abreviações comuns
   (`Dr.`, `Prof.`, `Av.`).
2. **Links do post como evidência prioritária.** `Post.links` reúne o card de link, os facets e as URLs do texto
   (hidratados no Bluesky antes da verificação). `_cited_evidence` lê até 2 matérias (redes sociais não contam) e as coloca
   à frente das buscas. O título da matéria vem do slug da URL, porque em portais de notícia o corpo nem sempre repete a manchete.
3. **Atalho para posts que só reproduzem a manchete da fonte que citam.** Se pelo menos 80% das palavras da alegação
   estão no título da matéria citada, a alegação é dada como `true` ("o post reproduz o título da matéria que ele próprio
   cita") e a busca aberta nem acontece. Se a fonte citada é relevante mas não é uma cópia da manchete, o classificador a avalia;
   se ela não confirma, entra no conjunto de evidências junto com as demais, o que ajuda a revelar post fora de contexto.
4. **Guarda de entidade** (`_entity_conflict`) no filtro de relevância: uma evidência é rejeitada quando ela e a alegação
   citam zona eleitoral ou pares cidade/UF e não têm nenhum em comum. Se a evidência não cita localidade nem zona, nada é
   concluído. Siglas de partido (`Lula (PT)`) não são tratadas como UF.

## Resultado do caso
Com as três correções, o post "Dom Pedro I" passou de `false` 94% para `true` pelo atalho do título, e os 7 posts
vizinhos da mesma família (outras escolas de Itacoatiara) também foram para `true`. Antes, vários deles saíam `misleading`.

## Limites conhecidos
- **O atalho do título não verifica o fato.** Ele diz que o post é fiel à fonte que cita. Se a fonte citada for errada ou
  enganosa e o post a copiar, o sistema não contesta. Rotular isso como `true` é uma simplificação: o valor existente mais
  próximo na enumeração de vereditos.
- **A guarda de entidade é uma heurística.** Só enxerga zona eleitoral e pares "Cidade (UF)" ou "Cidade/UF". Homônimos
  que não se distinguem por esses dados (por exemplo, duas pessoas com o mesmo nome) não são detectados. Um casamento de
  entidades completo (nome, município, UF, tipo) não foi implementado.
- **Limiar de 0,8 de cobertura sem calibração.** Foi validado em 8 posts de uma família de posts (manchetes do G1), não
  em um conjunto anotado. Não foi medido o caso de um post que distorce o que a matéria citada diz.
- O título vem do slug da URL; portais com slugs curtos ou numéricos caem no começo do texto da matéria.
- Vale só para o backend `jev`; o backend `llm` não lê `Post.links`.
- Posts novos demais para estarem indexados pelos buscadores não foram tratados com um peso de recência próprio.

## Consequências
- `Post` ganhou o campo opcional `links` (contrato de domínio: avisar as outras trilhas no PR).
- A análise faz uma chamada a mais ao Bluesky (`getPosts`) e, quando há link, uma busca da matéria.
- Fica uma regressão com o caso real nos testes (`test_jev_verification.py`, `test_bluesky_client.py`).

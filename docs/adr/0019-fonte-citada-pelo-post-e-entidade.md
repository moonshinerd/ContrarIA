# 0019 — Fonte citada pelo post e checagem de entidade

- **Status:** Aceita
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF01, RF03, GQ03

## Contexto
Em 05/10/2026 o bot publicou um quote post errado sobre um post de uma conta que republica manchetes do G1
("Resultado das eleições 2026 em Itacoatiara (AM): votação para presidente no E. M. Dom Pedro I, na 3ª zona eleitoral").
Ele afirmava que a reportagem situava a escola na 48ª zona eleitoral (Maribondo/AL). Existem duas escolas com o mesmo
nome em estados diferentes: o post estava correto, e o link dele apontava para a matéria certa. O post foi apagado.

Reproduzido localmente, o veredito saiu `false` com 94%. Três causas, todas confirmadas no código:

1. **Divisão de frases.** O divisor cortava depois de "E." (de "E. M."), e a alegação virou "Dom Pedro I, na 3ª zona
   eleitoral", sem a cidade. Esse fragmento casa com qualquer escola homônima.
2. **A fonte do próprio post não entrava como evidência.** O link do card nunca era lido.
3. **Evidência sobre outra entidade era aceita.** Uma página sobre a escola de Maribondo/AL passou pelos filtros e o
   classificador a tratou como desmentido.

A primeira correção, feita às pressas (PR #61), usava regex e uma regra de "cobertura do título ≥ 80%" que dava o post
como `true`. Foi descartada por ser frágil e por poder silenciar o sistema quando um post repete uma fonte duvidosa.
Esta decisão a substitui por métodos documentados na literatura.

## Pesquisa
- **Segmentação de frases.** O pySBD (regras, superior ao Punkt e ao spaCy em benchmark) [não tem português](https://arxiv.org/pdf/2010.09657),
  e o [sentencex](https://github.com/wikimedia/sentencex) (Wikimedia) ainda corta em `Min.` e `E.E.I.E.F.` nos nossos textos
  (testado). Ficou uma regra própria, com a lista de abreviações do jornalismo brasileiro, a mesma ideia do Punkt.
- **NLI entre alegação e documento.** [SummaC](https://aclanthology.org/2022.tacl-1.10/) e [AlignScore](https://arxiv.org/pdf/2305.16739)
  segmentam o documento em trechos, pontuam cada trecho contra a alegação e ficam com o **máximo**, porque NLI
  treinado em pares de frases perde sinal com documento inteiro.
- **Topônimos ambíguos.** A literatura de geoparsing ([levantamento](https://joiv.org/index.php/joiv/article/download/2763/1236))
  recomenda gazetteer, contexto hierárquico (cidade + estado) e "um sentido por discurso": a localidade do texto todo
  vale para cada fragmento. O trabalho de [desambiguação de entidades na verificação de fatos](https://arxiv.org/html/2505.22993)
  trata homônimos como uma causa clássica de erro.

## Decisão
1. **Segmentador de frases** (`app/domain/sentences.py`): não há fronteira depois de abreviação (`Dr.`, `Sen.`, `Min.`),
   de sigla de uma letra (`E. M.`), de sequência de iniciais (`E.E.I.E.F.`) nem quando a frase seguinte começa em minúscula
   (`5 de out. de 2026`).
2. **Gazetteer do IBGE** (`app/domain/geo.py`, dados em `app/domain/data/municipios_br.json`, 5.571 municípios, gerados
   por `app.scripts.build_gazetteer`). Extrai pares (município, UF) validados no gazetteer (então `Lula (PT)` não vira
   lugar), aceita nome único sem UF quando vem em maiúscula e depois de preposição de lugar, e ignora nomes ambíguos.
3. **Guarda de entidade com o contexto do post inteiro.** Uma evidência é rejeitada quando ela e o **post** (não só o
   fragmento verificado) citam localidade ou zona eleitoral e não têm nenhuma em comum. Matéria que lista muitas localidades
   (mais de 3) não é tratada como "outro lugar". Mesmo que o divisor perca a cidade de um fragmento, ela continua valendo.
4. **Fonte citada pelo post.** `Post.links` reúne o card de link, os facets e as URLs do texto (hidratados no Bluesky).
   `_cited_evidence` lê até 2 matérias (redes sociais não contam). O NLI compara a alegação com o título (extraído do slug
   da URL) e com janelas de duas frases da matéria, e fica com o maior entailment. Se passa de
   `CITED_SOURCE_ENTAILMENT_MIN` (0,7) **e** a fonte é jornalística, de checagem ou oficial
   (`CITED_SOURCE_MIN_AUTHORITY`), o veredito é `source_consistent` e a busca aberta não acontece. Em qualquer outro caso
   (fonte desconhecida, entailment baixo), a matéria entra como mais uma evidência e a verificação segue.
5. **Novo rótulo `source_consistent`:** "o post é consistente com a matéria que ele cita; a veracidade da matéria não foi
   avaliada". É uma ação de monitoramento, sem intervenção. Evita o `true`, que afirmaria o que não foi verificado.

## Medições
Avaliação reproduzível: `python -m app.scripts.eval_cited_support` (40 posts da família "Resultado das eleições…" com a
matéria lida, contra três adulterações de cada post: outra escola, outra zona e outra cidade).

| Limiar | Recall (post original) | Falsos aceites (outra zona / escola / cidade) |
|---|---|---|
| 0,5 | 0,97 | 0,00 / 0,00 / 0,03 |
| **0,7** | **0,93** | **0,00 / 0,00 / 0,00** |
| 0,8 | 0,60 | 0,00 / 0,00 / 0,00 |
| 0,9 | 0,10 | 0,00 / 0,00 / 0,00 |

Regressão: o verificador **antigo** e o **novo** sobre os mesmos 142 posts de decisões adversas anteriores, no mesmo momento.

| Grupo | Adversos ≥ 0,8 antes | Depois |
|---|---|---|
| Família G1 (30 posts) | 15 | **0** (29 viraram `source_consistent`, 1 ficou `misleading` a 0,43) |
| Fora da família (111 posts) | 31 | 30 (5 perdidos: 3 viraram `insufficient_evidence` e 2 `true`; 4 ganhos) |
| Quotes já publicados que ainda existem (15) | 4 | 3 |

Um dos "ganhos" é o post de um blog partidário: antes saía `true` a 52% e agora `false` a 95%, porque uma fonte sem
autoridade reconhecida não blinda o post. Auditorias adicionais: o novo divisor muda o resultado em 0,79% de 20 mil posts
(as amostras são cortes corretos), e a guarda de entidade rejeitaria 0,5% dos pares de evidência que o filtro antigo
aceitava (todas as amostras são mesmo outra cidade).

## Limites conhecidos
- **O ruído da web não foi medido.** O controle (rodar o código antigo duas vezes para ver quanto o resultado varia sozinho)
  foi interrompido. As diferenças fora da família G1 (5 perdidos e 4 ganhos em 111) não podem ser atribuídas com segurança
  à mudança nem ao ruído.
- **O limiar de 0,7 foi medido numa única família de posts** (manchetes do G1). Não foi medido o caso de um post que
  distorce o que a matéria citada diz, que é o "tirando do contexto".
- **A calibração CRC do Jev não foi refeita.** A guarda de entidade, o divisor e a fonte citada mudam a distribuição de
  evidências e de confiança em que a calibração se baseou.
- A guarda só reconhece município e zona eleitoral. Homônimos que não se distinguem por esses dados (duas pessoas com o mesmo
  nome, por exemplo) não são detectados. Um casamento de entidades completo (nome, município, UF, tipo) não foi feito.
- O título vem do slug da URL; portais com slug curto ou numérico caem no começo do texto da matéria. Se a matéria não puder
  ser baixada (paywall), o atalho não age.
- Vale só para o backend `jev`; o backend `llm` não lê `Post.links`.
- Posts novos demais para estarem indexados pelos buscadores não receberam um peso de recência próprio.

## Consequências
- `Post` ganhou o campo opcional `links` e `VerdictLabel` ganhou `source_consistent` (contrato de domínio: avisar as outras
  trilhas). O log de decisões grava `source_consistent` como string no campo `verdict`.
- A análise faz uma chamada a mais ao Bluesky (`getPosts`) e, quando há link, uma busca da matéria e um lote de NLI.
- Há duas variáveis novas (`CITED_SOURCE_ENTAILMENT_MIN`, `CITED_SOURCE_MIN_AUTHORITY`) e um arquivo de dados de 84 KB.
- Fica uma regressão com o caso real nos testes (`test_jev_verification.py`, `test_geo.py`, `test_sentences.py`).

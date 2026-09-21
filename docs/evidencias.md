# Fontes de evidência: web e RSS

Implementação da issue #21, conforme a porta `EvidenceSource`, sem alterar `Evidence`.
O pipeline pode usar `web_search` para notícias e `rss_checkers` para o acervo semântico.
Essas fontes recuperam evidências; não emitem vereditos.

## Uso

Na pasta `api`, depois de `uv sync` e com PostgreSQL/pgvector disponível:

```bash
uv run alembic upgrade head
uv run python -m app.jobs.ingest_fact_articles --min-articles 100
uv run python -m app.jobs.validate_rss_evidence \
  --cases ../research/evidence_queries.json \
  --output ../research/evidence_validation.json
```

Para executar localmente, configure `DATABASE_URL` com host `localhost`; o exemplo
`api/.env.example` usa host `db` para Docker. Com Docker, execute primeiro
`docker compose up -d db`, depois `docker compose run --rm api alembic upgrade head`
e finalmente `docker compose up -d api worker`. O worker coleta no início e repete
a cada `RSS_POLL_SECONDS` (padrão: uma hora). A imagem precisa ser reconstruída
após adicionar as dependências (`docker compose build`).

```python
from app.clients.evidence import get_evidence_source

# Dentro de uma função async; reutilizar as instâncias para aproveitar o cache.
web = get_evidence_source("web_search")
rss = get_evidence_source("rss_checkers")
noticias = await web.search("alegação a verificar", limit=5)
checagens = await rss.search("alegação a verificar", limit=5)
```

O PR #37 da issue #20 ainda estava aberto durante esta implementação. Ao integrá-lo,
manter no registro central também `google_factcheck` e `wikipedia`, sem remover as
quatro entradas desta issue. O contrato de domínio compartilhado não mudou.

## Busca web e custo

[Tavily](https://docs.tavily.com/documentation/api-reference/endpoint/search) recebe
`topic=news`, `search_depth=basic`, `days=WEB_SEARCH_DAYS`, `max_results` (até 20)
e autenticação Bearer. `web_search` tenta DuckDuckGo quando Tavily não tem chave,
está desligado, retorna vazio ou falha. Respostas 429, 432 e 433 suspendem novas
chamadas Tavily durante `TAVILY_COOLDOWN_SECONDS` (uma hora por padrão).

O [ddgs](https://github.com/deedy5/ddgs) tenta notícias e, quando não há resultados,
busca páginas gerais com a mesma consulta, `region=br-pt` e backend
`duckduckgo` explícito. O retorno `href` da busca geral é normalizado para a URL da
evidência; datas ausentes permanecem sem data. A mensagem `No results found.` é
tratada como resultado vazio, enquanto erros de rede, timeout e cota continuam
sendo falhas e não entram no cache. Não exige chave. As chamadas síncronas ficam fora do loop
async. Falhas dos dois provedores resultam em lista vazia, com aviso nos logs.
Consultas e chaves não são registradas nos avisos. Interfaces que precisam distinguir
falha de ausência de resultados podem usar `WebSearchSource(settings,
raise_on_failure=True)`, que lança `EvidenceSearchUnavailable` quando não há
resultados e algum provedor falhou. Consultas longas ainda podem não encontrar
correspondências; a busca não reformula nem altera a alegação automaticamente.

Cada provedor tem cache LRU em memória: 1.000 entradas e TTL de uma hora por padrão,
incluindo resultados vazios. Chamadas simultâneas à mesma consulta reutilizam o
resultado. O cache é por processo e se perde ao reiniciar; não é um contador de
créditos nem um limite financeiro global. Instanciar a fonte uma vez por processo.
O free tier citado na issue não é tratado como garantia de disponibilidade;
a cota real depende da conta Tavily. A chamada real autenticada precisa de
`TAVILY_API_KEY`; os testes cobrem requisição, resposta e erros com HTTP simulado.

## Feeds e disponibilidade

Verificação HTTP + parsing RSS em 21/09/2026:

| Fonte/config | URL consultada | Resultado |
| --- | --- | --- |
| `lupa` | <https://lupa.uol.com.br/feed> | RSS válido, 10 entradas; redireciona para Agência Lupa |
| `aos_fatos` | <https://www.aosfatos.org/noticias/feed/> | RSS válido, 20 entradas |
| `g1_fato_fake` | <https://g1.globo.com/rss/g1/fato-ou-fake/> | RSS válido, 100 entradas |
| `boatos` | <https://www.boatos.org/feed> | RSS válido, 25 entradas |
| `comprova` | <https://projetocomprova.com.br/feed/> | RSS válido, 3 entradas |
| `tse` | <https://www.tse.jus.br/comunicacao/noticias/RSS> | HTTP 403 nesta rede; coleta configurada, sem artigos importados |
| `estadao_verifica` | <https://www.estadao.com.br/estadao-verifica/feed/> | HTML, sem feed confirmado; desabilitado por padrão |
| `uol_confere` | <https://rss.uol.com.br/feed/noticias/confere.xml> | HTML, sem feed confirmado; desabilitado por padrão |

Os cinco feeds acessíveis geraram 158 artigos únicos na execução inicial. As
quantidades variam com o tempo; não existe garantia de que todo feed publique
100 artigos em uma única execução. A base acumula artigos entre execuções.
O coletor rejeita HTML e isola falhas por fonte. Feed indisponível aparece em
`errors`; não é contado como importação bem-sucedida.

`TAVILY_ENABLED`, `DUCKDUCKGO_ENABLED` e `RSS_CHECKERS_ENABLED` controlam cada
adaptador. `RSS_ENABLED_SOURCES` é uma lista JSON: remover um nome desativa tanto
a coleta quanto a recuperação de artigos já armazenados daquela origem.
`RSS_FEED_URLS` permite sobrescrever URLs por nome. Para habilitar UOL/Estadão,
primeiro confirmar um feed RSS/Atom válido e informar seu endereço nesse mapa.
Não há raspagem de páginas HTML como substituição silenciosa de RSS.

## Decisão: embeddings locais e ranking

Modelo escolhido:
[`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
384 dimensões, execução em CPU e vetores normalizados. Isso dispensa chave e custo
por requisição. O primeiro uso baixa os pesos; usos seguintes aproveitam o cache
local, persistido no volume `contraria-model-cache` no Docker. O modelo consome
memória e aumenta a imagem da aplicação; deve ser carregado uma vez por processo.
Trocar o modelo exige reindexar os artigos, mesmo que a dimensão permaneça igual.
O lock usa o índice oficial PyTorch CPU no Linux, evitando instalar CUDA no
servidor e no CI, conforme a [configuração do uv](https://docs.astral.sh/uv/guides/integration/pytorch/).

A migration cria a extensão `vector` e a tabela `fact_articles` com URL como chave
primária. Guarda origem, título, resumo do feed (até 3.000 caracteres), data UTC
quando disponível e embedding. URLs repetidas são atualizadas; textos e datas
inalterados não recalculam embeddings. O coletor não inventa datas de publicação.

A busca calcula similaridade cosseno no PostgreSQL e aplica:

```text
score = (1 - peso) × similaridade + peso × 0.5^(idade_em_dias / meia_vida)
```

Padrões: peso 0,1, meia-vida 30 dias e similaridade mínima 0,3. Documentos sem data
recebem bônus zero; datas futuras têm idade limitada a zero. A similaridade mínima
é aplicada antes do bônus para que a recência não promova conteúdo sem relação.
Ordenação por URL desempata resultados. A busca é exata: não usa índice aproximado
neste acervo pequeno, evitando perda de recall com filtros e bônus de recência.

## Validação reproduzível

Os testes unitários usam fakes, sem internet nem download do modelo. Para também
executar os testes de integração, aponte `TEST_DATABASE_URL` para um banco de testes
com pgvector e execute `make lint test`. Esses testes revertem suas transações.
A configuração adicional do CI inicia PostgreSQL/pgvector e verifica também
upgrade, downgrade e novo upgrade. Ela foi preparada localmente em
`.github/workflows/ci.yml`, mas não está no PR: a credencial GitHub disponível
não tem escopo `workflow`. Até essa configuração ser enviada por uma credencial
autorizada, os testes PostgreSQL são executados localmente e pulados no CI sem
`TEST_DATABASE_URL`.

O smoke test usa cinco alegações parafraseadas e URLs esperadas em
`research/evidence_queries.json`. Exige pelo menos 100 artigos e a URL relevante
entre os cinco primeiros resultados de cada alegação. O relatório é gravado por
`validate_rss_evidence`; código de saída 1 indica falha. Os casos foram escolhidos
entre assuntos presentes nos feeds desta coleta, não constituem um benchmark
independente de qualidade ou de veracidade. Após os artigos saírem dos feeds, uma
base nova pode exigir novos casos; preservar o acervo permite repetir esta amostra.

Resultado desta execução: **158 artigos, 5/5 alegações com acerto no top 5**.
A segunda coleta atualizou **zero** artigos e manteve 158, confirmando idempotência
sem recalcular os embeddings. Relatório completo: `research/evidence_validation.json`.
DuckDuckGo retornou três notícias numa consulta real; Tavily foi validado com mocks,
pois não havia uma chave configurada para executar a chamada autenticada.

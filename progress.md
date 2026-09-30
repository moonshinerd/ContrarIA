# PR #50 — validação manual, correções e encerramento técnico

Data: 23/09/2026. PR: [#50](https://github.com/moonshinerd/ContrarIA/pull/50), branch `feat/issue-11-jetstream-poller`.

## Resultado final

As pendências de código e configuração versionada encontradas na revisão foram corrigidas nesta branch. A coleta, persistência, cursor, refresh, bot score em cache e intervenção em dry-run foram reexecutados contra serviços reais. O código também passou em lint, formatação e compilação.

O único trabalho restante é operacional: criar/acessar a VPS Oracle escolhida, apontar DNS público, cadastrar secrets de SSH e fazer o primeiro deploy. Esses recursos e permissões não existem neste checkout; por isso não é possível provar certificado público ou execução de CD antes do provisionamento. O compose agora falha intencionalmente se os domínios não forem informados, evitando o antigo deploy com placeholders.

## Escopo e segurança

- A revisão confrontou cada requisito das issues #11–#15 com o código.
- Os fluxos abaixo foram executados manualmente, não por `pytest`/cobertura.
- Credenciais Bluesky já configuradas foram usadas sem serem lidas ou exibidas.
- Foram gravados somente dados públicos na base Docker local de validação. Nenhuma publicação, like, repost ou quote remoto foi criado.
- Para a intervenção foi usado `INTERVENTION_DRY_RUN=true`; a saída foi gerada pelo LLM real, mas não enviada ao Bluesky.

## Evidências de execução ao vivo

| Fluxo | Evidência observada | Resultado |
|---|---|---|
| Login e leitura Bluesky | busca `top` em PT/24 h retornou 3 posts; `getPosts`, perfil, feed e postgate responderam | OK |
| Jetstream | conexão TLS estabelecida; uma janela obteve 1 candidato PT/político válido após 131 eventos | OK |
| Poller + persistência | busca real retornou 25 posts; primeira gravação inseriu 25 e reaplicar o lote inseriu 0 | OK |
| Refresh | 25 candidatos, 25 hidratações, 25 snapshots e 25 triagens persistidos | OK |
| Jetstream + cursor | 629 eventos e 1 candidato gravado; após correção, evento não elegível também persistiu `time_us` | OK |
| Bot score novo | score em `[0,1]` e 12 features calculadas | OK |
| Bot score em cache | conta já cacheada retornou score/12 features sem exceção | OK |
| Intervenção dry-run | LLM real retornou `dry_run_uri`; publicação confirmada como `no` | OK |
| Worker ponta a ponta | janela local de 27 s conectou Jetstream, executou poller/refresh/LLM/Self-RAG e processou candidato até `monitor`, sem erro fatal | OK |
| API local | `GET /health` retornou `{"status":"ok"}` | OK |
| Compose/Caddy | Compose resolveu com domínios de teste; `caddy validate` retornou `Valid configuration` | OK |

Verificações locais complementares: `ruff check`, `ruff format --check` e `python -m compileall` passaram.

## Correções aplicadas por issue

### #11 — Jetstream e poller

Concluído no repositório.

- O consumer já filtrava commits de criação, idioma, termos políticos, URI e persistência idempotente.
- O filtro agora aceita variantes como `pt-BR`, não somente `pt` (`api/app/jobs/collector.py`).
- O `time_us` é persistido para todo evento, inclusive descartado; o cursor não fica preso em períodos sem candidatos.
- Em reconexões, a URL é reconstruída com o cursor corrente e mantém recuo idempotente de cinco segundos.
- Busca `top`, janela de 24 h e deduplicação foram confirmadas com API/Postgres reais.

### #12 — engajamento e matriz GQ04

Concluído no repositório.

- Tópicos, snapshots, velocidade e relevância foram exercitados com dados reais.
- Thresholds saíram de literais e foram configurados em `Settings`/`.env.example`.
- `PostRepository.get_triage_candidates()` fornece fila ordenada; `update_triage()` persiste o resultado.
- O novo `TriagePipeline`, conectado ao worker, agrega perfil/seguidores, bot score, veredito, risco público e GQ04 antes de atualizar a fila.
- O tamanho do lote por ciclo é configurável para controlar custo de LLM.

### #13 — bot scoring

Concluído no repositório.

- Corrigido o TTL do cache: timestamp timezone-aware é subtraído corretamente antes de `total_seconds()`.
- A correção foi validada ao vivo contra uma conta já cacheada.
- Conteúdo duplicado agora usa Jaccard de shingles de três tokens e detecta quase-duplicatas, além de cópias exatas.
- O pipeline consome o score para priorização e tom de intervenção.

### #14 — intervenção

Concluído no repositório para o caminho seguro de execução.

- O serviço usa `LLMPort.complete(...)`, método implementado por `LiteLLMModel`, em vez de `generate(...)` inexistente.
- O dry-run real passou e não registra uma publicação como se tivesse ocorrido; portanto não consome anti-loop/limite diário de quote real.
- Foram adicionados guardrails para texto vazio/agressivo, truncamento por grafemas aproximados e orçamento diário configurável de pontos de escrita.
- Falhas inesperadas de postgate bloqueiam publicação; ausência normal do record significa “sem postgate”.
- O worker cria `TriagePipeline` e somente chama intervenção depois de bot score, verificação e triagem `queued`.
- Quote público real não foi publicado: falta uma conta-alvo de teste autorizada e não se publica um veredito fabricado contra usuário público. O caminho até a escrita foi validado ao vivo em dry-run.

### #15 — deploy

Concluído no repositório; provisionamento externo pendente.

- Compose de produção e Caddy foram validados com imagem oficial.
- `API_DOMAIN` e `OZONE_DOMAIN` são obrigatórios; removidos defaults `*.local`.
- A ADR escolhe Oracle Cloud Free Tier ARM e documenta instância/IP, DNS e secrets de SSH como itens externos.
- O workflow continua acionado por `push` em `main`, constrói a stack e aplica migrations.

## Fluxo final no worker

```text
Jetstream/SearchPoller → Postgres → refresh de engajamento
  → fila ordenada → bot score + perfil/seguidores + verificação
  → GQ04 → intervenção dry-run/quote com guardrails
```

O pipeline limita o lote e é protegido por orçamento. Em falha de um candidato, o worker registra o erro e continua os demais.

Durante a validação, respostas estruturadas inválidas do LLM e respostas Self-RAG sem ancoragem foram convertidas em `INSUFFICIENT_EVIDENCE`; isso é uma abstenção segura, não uma intervenção. O pipeline não publica em caso de evidência insuficiente.

## Pendência operacional para o primeiro deploy público

1. Provisionar a VM Oracle Cloud Free Tier ARM e instalar Docker/Compose.
2. Definir `API_DOMAIN` e `OZONE_DOMAIN` no `.env` exclusivo do servidor.
3. Criar DNS na Cloudflare e aguardar propagação.
4. Cadastrar `SSH_HOST`, `SSH_USER` e `SSH_KEY` nos secrets do GitHub.
5. Fazer merge na `main`, acompanhar o primeiro workflow e validar `https://$API_DOMAIN/health`.
6. Para quote real, informar conta Bluesky de teste autorizada e veredito/evidência de teste aprovados.

## Limpeza

Os contêineres de validação foram parados ao término. Volumes locais foram preservados; nenhum recurso remoto foi removido ou alterado.

---

# Acompanhamento operacional — backend Jev e segurança de intervenções

Atualizado em 30/09/2026 (horário de Brasília). Esta seção é o registro vivo
do trabalho atual e deve ser atualizada a cada teste, mudança relevante ou
decisão operacional.

## Estado atual

- O Docker Desktop, que estava desligado após o Mac ser desligado, foi iniciado.
  `db`, `api`, `worker` e `jev` estão saudáveis.
- O worker está com `VERIFICATION_BACKEND=jev` e publicação real habilitada.
  O Jev usa Qwen3-4B GGUF em um único serviço compartilhado; API e worker não
  carregam cópias separadas do modelo.
- A calibração CRC do Jev está registrada com 40 exemplos e `alpha=0,05`.
- A documentação da arquitetura Jev foi consolidada e enviada ao PR
  [#57](https://github.com/moonshinerd/ContrarIA/pull/57) no commit `11f04cb`.
  A `main` já estava incorporada ao branch no momento da conferência.

## Reconciliação com o Bluesky

O banco tinha registros de quotes que haviam sido apagados manualmente no
Bluesky. A fonte de verdade usada foi a API pública
`app.bsky.feed.getAuthorFeed` do perfil `@contraria-bot.bsky.social`.

- Nove registros operacionais antigos de quote foram removidos em uma primeira
  reconciliação; o histórico de decisões foi preservado e recebeu revisões
  `QUOTE_REMOVED_MANUALLY`.
- O quote sobre o **Bloco Amantes Latinos em Barcelona** foi apagado pelo
  operador depois. A API confirmou a remoção e mais um registro operacional foi
  removido; a decisão `623` recebeu revisão explícita de remoção manual.
- No momento desta atualização, a API confirma **três** quotes publicados. O
  banco operacional (`intervention_logs`) contém exatamente esses três.
- Não apagar decisões históricas é intencional: elas registram que a ação foi
  tomada. A revisão registra que a publicação deixou de existir; o registro
  operacional controla a prevenção de duplicidade.

Após essa reconciliação, uma rodada antiga que já estava em memória publicou
mais um quote às 09:15 (Brasília). A API e `intervention_logs` confirmam
**quatro** quotes no momento desta atualização; esse quarto item não passou
pela correção nova e deve ser revisado separadamente se houver dúvida sobre o
conteúdo.

## Incidente encontrado: falso positivo de Barcelona

O post original dizia que o Bloco Amantes Latinos estava em Barcelona naquele
dia. O Jev classificou-o como `false` com confiança de aproximadamente 100% e
o pipeline publicou uma pergunta baseada em Fernanda Serrano.

A auditoria da decisão `623` mostrou que as cinco fontes aceitas não tratavam
do bloco nem do evento: incluíam checagens sobre Cristiano Ronaldo e clubes
brasileiros, uma fábrica em Barcelona, uma instituição portuguesa e a página
da atriz Fernanda Serrano. Esta última somente menciona uma participação em
filme rodado em Barcelona em 1996; não confirma o evento nem sustenta a frase
gerada pelo LLM de que ela seria uma pessoa capaz de confirmá-lo.

Conclusão: não foi apenas um limiar de confiança inadequado. O sistema aceitou
relevância por coincidência geográfica/temática e converteu ausência de
confirmação em desmentido. O quote foi corretamente removido pelo operador.

## Correção em implementação

Arquivos alterados, ainda não commitados nesta etapa:

- `api/app/services/jev_verification.py`
  - Fontes agora precisam compartilhar pelo menos duas âncoras factuais com a
    alegação antes de chegarem ao Jev. Cidade, país ou tema isolado não bastam.
  - Hashtags em linha isolada não entram como alegações factuais candidatas.
  - Alegações temporais explícitas (`hoje`, `ontem`, `agora`, etc.) recebem a
    data original do post na consulta e no prompt de relevância. A data não é
    um filtro rígido: fontes posteriores podem continuar refutando um post
    antigo se tratarem diretamente do fato daquela data.
- `api/tests/test_jev_verification.py`
  - Teste de regressão para o caso Barcelona: fontes que só mencionam a cidade
    são rejeitadas antes de consumirem inferência Jev.
  - Teste para ignorar hashtags isoladas e teste para incluir a data em
    alegações temporais.

Validação já concluída: `pytest tests/test_jev_verification.py` (**10 passed**),
`ruff check` e `ruff format --check` passaram.

## Reteste em andamento

O post de Barcelona está sendo reprocessado somente para leitura com a nova
versão do Jev. O teste não chama publicação, fila, Ozone nem escrita no banco.
Resultado esperado: `insufficient_evidence`, porque nenhuma fonte contém
âncoras diretas do bloco e do evento. Registrar aqui o resultado antes de
commitar a correção.

### Resultado parcial do reteste

O primeiro reteste ainda retornou `false`. A auditoria mostrou uma segunda
brecha: além da frase do evento, o post era separado em `Núcleo PT Barcelona`
e `Comitê Lula Presidente - Barcelona`; esses identificadores de campanha
podiam encontrar coincidências genéricas e chegar ao veredito. A correção foi
endurecida antes do commit: uma fonte agora precisa compartilhar uma expressão
de duas palavras consecutivas **e** pelo menos duas âncoras factuais; linhas de
`Núcleo`/`Comitê` são descartadas como identificadores, não alegações. Um novo
reteste de Barcelona será registrado aqui após os testes unitários.

### Aplicação da correção no worker

O worker precisa ser reiniciado para importar mudanças em `api/app`: ele não
usa reload. Antes do restart, uma rodada já calculada pelo código antigo
publicou um quote às 09:15 (Brasília); ela não é resultado da correção nova.
O worker foi reiniciado às 09:16, retomou a sessão e a coleta normalmente, e
os candidatos que existiam apenas na fila em memória foram descartados. A
partir desse ponto, novas análises usam as regras de âncora, expressão factual,
identificador de campanha e data do post.

### Reteste final de Barcelona

Depois do endurecimento, o mesmo snapshot da decisão `623` foi reprocessado em
modo somente leitura. Resultado: `insufficient_evidence`, confiança `0,0`,
alegação avaliada `Hoje em Barcelona, Bloco Amantes Latinos aquecendo os
tambores!!!!!` e zero evidências relevantes. Nenhuma publicação, fila, Ozone
ou escrita no banco foi acionada pelo reteste. Este é o comportamento esperado:
ausência de fonte diretamente relacionada ao evento causa abstenção, não
desmentido.

### Validação final da correção

- Teste unitário focado: `11 passed` em `tests/test_jev_verification.py`.
- Suíte completa no contêiner, com o dataset de pesquisa montado como o teste
  exige: `196 passed, 2 skipped`.
- `ruff check` e `ruff format --check` passaram para todo o projeto da API.
- O primeiro comando da suíte sem o volume `/research` falhou somente porque
  `test_claim_verification.py` procura o arquivo de golden set nesse caminho;
  a repetição com o volume correto passou integralmente.

### Entrega da correção

A correção foi commitada e enviada ao PR
[#57](https://github.com/moonshinerd/ContrarIA/pull/57) no commit `a162082`
(`fix: exigir evidência diretamente relacionada no Jev`). O commit contém as
travas de relevância, o contexto temporal, os testes de regressão e este diário
operacional. `conversa.md` e `tmp/` permanecem locais e não versionados.

## Próximas ações planejadas

1. Concluir e registrar o reteste de Barcelona.
2. Commitar e enviar a correção ao PR #57, após validação completa adequada.
3. Construir um conjunto de avaliação separado para `deve_responder`, com
   exemplos benignos e difíceis: relatos locais, eventos sem cobertura
   jornalística, postagens políticas comuns, opinião e sátira.
4. Recalibrar o CRC somente depois de aumentar e estratificar o conjunto. O
   conjunto atual tem 40 exemplos (apenas seis verdadeiros) e permite um falso
   positivo de alta confiança dentro da margem estatística de 5%; ele não mede
   bem o gate semântico de intervenção.

## Incidente Benedita da Silva — 30/09/2026

Foi identificada a decisão `624`, que classificou como `false` (confiança
`0,999998785`) uma postagem que dizia que Benedita da Silva concorria ao Senado
do Rio. A fonte principal já era uma matéria do g1 cujo trecho de busca dizia
expressamente que ela participou do debate como candidata ao Senado. Ainda
assim, o redator Gemini 2.5 Flash publicou um questionamento.

### Causa confirmada

Antes desta correção, o redator recebia no prompt apenas título, URL e os
primeiros 300 caracteres de cada fonte. Ele *podia* chamar a ferramenta
`ler_materia` para receber até 15.000 caracteres, mas isso era opcional. Os
logs da decisão `624` não contêm a chamada de leitura; portanto a entrevista/
matéria não foi enviada integralmente ao modelo. Isso não explica sozinho o
erro — o trecho já confirmava a candidatura —, mas remove uma barreira
essencial para decisões fundamentadas.

### Correção em implementação

O serviço passou a buscar obrigatoriamente, antes da geração, o texto extraído
das até três fontes de evidência mais relevantes (máximo de 15.000 caracteres
por matéria) e a incluí-lo no prompt. Se nenhuma fonte puder ser lida, ele se
abstém. A ferramenta passa a apenas repetir texto que já foi fornecido: o
redator não pode mais optar por decidir somente com snippets. O modelo de
redação será trocado de `openrouter/google/gemini-2.5-flash` para
`openrouter/openai/gpt-5-mini`, mantendo o gateway OpenRouter e as credenciais
atuais.

### Validação da troca

- Testes focados de intervenção: `19 passed`.
- `ruff check` e `ruff format --check` passaram nos arquivos alterados.
- Smoke test real via OpenRouter: `openrouter/openai/gpt-5-mini` respondeu
  `ContrarIA online`; o rastreador registrou custo de US$ `0,0006`.
- O modelo foi confirmado no catálogo do gateway com contexto de 400.000
  tokens. A página oficial da OpenAI o descreve como apropriado para tarefas
  bem definidas, de baixa latência e alto volume; ele suporta function calling
  e structured outputs. A troca não é uma garantia de veracidade: as novas
  travas de leitura obrigatória e abstenção são a proteção determinística
  contra decidir por snippet.

Próximo passo: rodar a suíte completa, reiniciar API e worker para reler
`api/.env`, e então commitar/enviar a correção e sua documentação ao PR.

### Análise adicional recebida sobre Benedita

O novo material confirma que a frase publicada pelo bot — “lista diferente de
n​​omes” — não é apenas uma dúvida fraca: a própria fonte g1 recuperada lista
Benedita da Silva como candidata ao Senado pelo Rio. O caso passa a ter três
regressões explícitas: (1) uma lista de debate não pode negar registro de
candidatura; (2) fonte que suporta a alegação não pode virar veredito adverso;
(3) o redator não pode inventar uma inconsistência ausente da evidência. O
exemplo será mantido como caso obrigatório de `SUPPORTED`/abstenção em testes.

### Revisão integral em lotes — implementação em andamento

Foi substituído o corte de 15.000 caracteres na função de extração: ela agora
retorna o texto integral por padrão. As até cinco fontes de evidência serão
divididas em lotes por orçamento de contexto, sem descartar caracteres, e cada
lote será lido pelo GPT-5 mini antes da geração final. A configuração adiciona
janela de 400.000 tokens e orçamento conservador de 320.000 tokens por lote
(três caracteres por token, cerca de 960.000 caracteres), deixando margem para
instruções e resposta. O prompt final agora recebe somente as notas dos lotes,
nunca snippets isolados; os testes e a formatação já foram concluídos.

### Distinção entre Jev e redator

O Jev opera com `JEV_N_CTX=4096`; é uma triagem local de contexto curto e não
deve ser tratado como leitor integral de cinco reportagens. O veredito adverso
dele neste caso é explicável como limitação de recuperação/entailment, embora
continue inadequado para publicação. O redator, por outro lado, recebeu uma
fonte cujo trecho já apoiava a alegação e mesmo assim inventou uma contradição.
Por isso a revisão integral em lotes no GPT-5 mini é uma barreira independente
e obrigatória entre o Jev e qualquer mensagem pública.

### Validação da implementação de lotes

A suíte completa passou após a mudança: `198 passed, 2 skipped`; `ruff check`
e `ruff format --check` também passaram. Os testes agora cobrem extração sem
corte padrão, abstenção quando nenhuma fonte pode ser lida, e preservação de
todo o texto quando uma matéria é dividida entre lotes.

### Limites dinâmicos pelo LiteLLM

Em vez de confiar somente em variável manual, o serviço agora consulta
`litellm.get_model_info()` para o identificador efetivo do modelo. A instalação
atual retornou para `openrouter/openai/gpt-5-mini`: `max_input_tokens=400000`
e `max_output_tokens=128000`. O orçamento de lote usa esse limite de entrada,
menos 16.000 tokens reservados, limitado pelo teto operacional de 320.000;
`LLM_CONTEXT_WINDOW_TOKENS=400000` permanece apenas como fallback para modelos
que o catálogo não conheça. Testes foram adicionados para o catálogo do
OpenRouter e para o fallback.

### Tetos de custo e conteúdo

O LiteLLM instalado informa 400.000 tokens de entrada para o identificador
OpenRouter em uso — não 1 milhão. Isso comporta reportagens extensas, mas não
autoriza entrada ilimitada. Foram definidos dois limites deliberadamente
generosos: até 320.000 tokens estimados por lote e, para a soma de até cinco
matérias, 2.500.000 caracteres e no máximo três lotes. Se qualquer teto for
excedido, o serviço se abstém; ele não corta texto silenciosamente nem manda um
documento gigantesco ao LLM. Foi incluído teste de regressão para essa
abstenção por custo.

### Validação final dos limites

Após isolar corretamente a configuração temporária do teste de teto, a suíte
completa ficou em `201 passed, 2 skipped`; `ruff check` e `ruff format --check`
passaram em toda a API. Próximo passo operacional: reiniciar API e worker para
carregar o GPT-5 mini e os limites de leitura integral configurados no `.env`.

### Ativação operacional

API e worker foram reiniciados após a validação. A API respondeu
`{"status":"ok"}`, banco e Jev permanecem saudáveis, e o worker retomou a
sessão Bluesky. Um candidato que estava somente na fila em memória expirou no
restart; ele não foi publicado. O `.env` local agora aponta o redator para
`openrouter/openai/gpt-5-mini`; credenciais continuam fora do Git.

### Entrega

A implementação foi commitada e enviada ao PR #57 no commit `e9c33af`
(`fix: revisar fontes integrais antes de intervir`). O commit contém o GPT-5
mini como padrão de redação, revisão integral em lotes, consulta de limites ao
LiteLLM, tetos de custo por caracteres/lotes, prompts, testes e documentação.

### Smoke test da etapa final

Foi executada uma chamada real, sem ferramentas, pelo mesmo modo de conclusão
usado após a revisão em lotes. O GPT-5 mini respondeu `modo final ok`; nenhuma
fila, decisão ou publicação Bluesky foi acionada. API, banco, Jev e worker
continuam em estado saudável.

## Reavaliação dos quotes ativos — 30/09/2026

A API pública do Bluesky retornou três quote posts ativos do ContrarIA. O quote
sobre Benedita da Silva não aparece mais. Os três posts originais são: voto
para o Senado (`3mwj3tdn4q224`), decisão de Flávio Dino (`3mwjc475ddc2j`)
e comentário sobre um suposto projeto antigo evangélico (`3mwdju7cejs2j`).
API, banco, Jev e worker seguem ativos. Iniciada reavaliação desses três posts
com a versão atual do Jev e, quando pertinente, a revisão integral em lotes e
o redator GPT-5 mini. A reprodução não deve publicar, enfileirar ou alterar
decisões existentes.

### Investigação do Jev

O reforço anterior do Jev (âncoras diretas entre alegação e fonte, expressão
factual compartilhada, contexto de data e exclusão de identificadores de
campanha) foi feito após Barcelona. Ele já estava ativo quando a decisão
`624` sobre Benedita foi tomada e não impediu o falso veredito: a fonte do g1
afirma que ela era candidata ao Senado. Portanto há trabalho específico de
interpretação de evidência a fazer no Jev. Um reteste somente leitura dos
três quotes ativos está em andamento; o caso Benedita será usado como
regressão para bloquear contradições diante de suporte explícito.

### Resultado parcial do replay

O post sobre o segundo voto para o Senado (decisão histórica `583`) foi
reprocessado com buscas atuais e o Jev atualizado. Resultado:
`insufficient_evidence`, confiança `0,0`, por ficar abaixo de `lambda_hat`.
Fontes encontradas: TSE, g1 e TRE-RS. Nessa execução o fluxo pararia antes do
redator e não repetiria o quote. Os outros dois posts seguem em processamento.

### Resultado do Jev para os três quotes ativos

- Segundo voto para o Senado (`583`): `insufficient_evidence`, confiança
  `0,0`, por ficar abaixo de `lambda_hat`.
- Decisão de Flávio Dino (`493`): `true`, confiança `0,9999997701`, na frase
  “A medida também se aplica a outras publicações censuradas.”; as duas fontes
  classificadas relevantes tratavam de bloqueio de apostas, não da decisão
  judicial. Não haveria quote, mas a seleção de evidências foi inadequada.
- “Projeto antigo do poder evangélico” (`467`):
  `insufficient_evidence`, confiança `0,0`, por não encontrar evidência
  diretamente relevante.

Portanto, com buscas atuais e o Jev desta execução, nenhum dos três avançaria
à redação/publicação. A revisão integral com GPT-5 mini será testada em
separado com as evidências das decisões históricas, como cenário contrafactual
de “e se o Jev tivesse deixado passar novamente?”. Esse teste será apenas de
leitura e geração, sem ações no Bluesky.

### Contrafactual do redator com as fontes históricas

O GPT-5 mini leu as páginas acessíveis das fontes das três decisões antigas
pela nova rotina integral em lotes, com publicação desativada:

- Segundo voto para o Senado (`583`): gerou novamente `DESMENTE` e um quote
  alternativo; portanto a barreira de redação não vetaria esse caso.
- Flávio Dino (`493`): respondeu `CONFIRMA` e vetou a publicação.
- Projeto evangélico (`467`): respondeu `CONFIRMA` e vetou a publicação.

Esse teste usa as fontes e os vereditos históricos como entrada, não a saída
atual do Jev. Parte das URLs originais já não pôde ser aberta; o redator usou
apenas textos efetivamente extraídos. Em especial, uma página da Poder360
devolveu só 257 caracteres, enquanto outras fontes do caso Dino retornaram
textos mais extensos. A divergência em relação à preferência do usuário será
avaliada como possível perda de cobertura, sem alterar o limiar estatístico às
cegas.

### Correção específica do Jev em andamento

Foi adicionada uma trava estreita: se a alegação afirma que uma pessoa concorre
ao Senado e uma fonte relevante a apresenta explicitamente como candidata ao
Senado, um veredito adverso do Jev causa abstenção. Isso captura o padrão da
Benedita sem concluir automaticamente que toda fonte é verdadeira. Testes
incluem o exemplo de suporte explícito, uma negação e o veto integrado. A
validação completa e o restart do worker ainda estão pendentes.

### Feedback sobre cobertura

O usuário considera os três quotes ainda ativos referências de intervenções
úteis. A abstenção dos três no replay com buscas atuais indica possível perda
de cobertura, mas não basta para julgar a qualidade das publicações antigas:
as fontes recuperadas em 30/09 diferem das fontes originais. O próximo
diagnóstico separa dois efeitos: (a) recuperação de evidência atual versus a
evidência salva na decisão histórica; (b) julgamento do Jev diante da mesma
evidência histórica. Não reduzir `lambda_hat` sem esse teste e sem reavaliar o
conjunto de calibração, para não repetir os erros de Barcelona/Benedita.

## Ponto de parada para continuidade manual — 30/09/2026

O trabalho foi pausado deliberadamente a pedido do usuário. O replay técnico
que estava rodando foi interrompido; ele não publicou, enfileirou nem alterou o
Bluesky ou o banco.

### Estado exato

- Os três quotes ativos no Bluesky continuam sendo `3mwj3tdn4q224` (segundo
  voto para o Senado), `3mwjc475ddc2j` (decisão de Flávio Dino) e
  `3mwdju7cejs2j` (projeto antigo do poder evangélico). O quote de Benedita foi
  apagado e não aparece no feed público.
- O replay atual com buscas novas do Jev terminou assim: Senado =
  `insufficient_evidence`; Dino = `true`, mas com evidências inadequadas sobre
  apostas; projeto evangélico = `insufficient_evidence`. Nenhum desses três
  avançaria para publicação nessa execução.
- O replay contrafactual do redator GPT-5 mini com as fontes históricas já
  terminou: Senado gerou novamente `DESMENTE`; Dino e projeto evangélico
  responderam `CONFIRMA` e seriam vetados. Foi dry-run, sem publicação.
- Um segundo replay contrafactual do Jev, usando as evidências históricas e a
  nova trava, foi interrompido durante `START 493`, depois de concluir o item
  `583`. Para `583`, o resultado bruto foi `misleading` com confiança
  `0,9002690953`, mas a calibração converteu para `insufficient_evidence` por
  estar abaixo de `lambda_hat`.
- A correção local do Jev está escrita, mas ainda não está entregue: a função
  `_explicit_candidate_support` detecta quando uma fonte relevante chama a
  pessoa de candidata ao Senado e transforma um veredito adverso conflitante
  em abstenção. Isso foi criado para o caso Benedita.
- Testes focados do Jev chegaram a `14 passed` antes de um ajuste pequeno de
  formatação. Depois desse ajuste, a suíte focada e a suíte completa ainda não
  foram executadas novamente.
- Há alterações não commitadas em `api/app/services/jev_verification.py`,
  `api/tests/test_jev_verification.py` e neste `progress.md`. `conversa.md` e
  `tmp/` continuam arquivos locais não versionados.

### Próximos passos recomendados

1. Rodar `pytest` focado de `tests/test_jev_verification.py` e `ruff check`/
   `ruff format --check` para validar a trava nova.
2. Rodar a suíte completa com `/research` montado; só prosseguir se todos os
   testes passarem.
3. Fazer um replay somente leitura do caso `624` da Benedita com as fontes
   históricas e confirmar que o Jev se abstém quando a fonte sustenta a
   candidatura.
4. Completar o replay histórico dos IDs `493`, `467` e `624`, registrando no
   `progress.md` o resultado bruto, o resultado após CRC e as fontes usadas.
5. Avaliar a seleção inadequada de fontes do caso Dino antes de mexer em
   `lambda_hat`; a correção provável é reforçar relevância/entailment, não
   simplesmente baixar o limiar.
6. Reiniciar o worker somente depois dos testes, observar logs sem publicar
   manualmente e então decidir se a trava do Jev deve ser commitada e enviada
   ao PR.

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

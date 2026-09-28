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

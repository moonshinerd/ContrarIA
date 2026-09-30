# ContrarIA

Bem-vindo ao repositório do **ContrarIA**, um projeto focado no combate à desinformação através do uso da Inteligência Artificial.

Este projeto está sendo desenvolvido como resposta ao **Challenge 1: Fake News / Desinformação**, seguindo a metodologia CBL (Challenge Based Learning).

## 🎯 A Grande Ideia (Big Idea)
Em um mundo com excesso de informação, como distinguir fatos, evidências e opiniões? A IA pode apoiar a investigação da confiabilidade das informações, fortalecendo o pensamento crítico em vez de substituí-lo.

**Pergunta Essencial:** 
> *"Como sistemas de IA podem ajudar as pessoas a avaliar a confiabilidade de informações sem substituir seu pensamento crítico?"*

---

## 💡 Nossas Abordagens em Pesquisa

Atualmente, estamos investigando as seguintes frentes de solução:
1. **Bot Socrático contra Desinformação / *Rage Bait*:** Um agente que, em vez de impor uma verdade absoluta, utiliza o Método Socrático para fazer perguntas reflexivas, estimulando o usuário a questionar a fonte da postagem viral.
2. **Classificador de Bots e Contas Inautênticas:** Um sistema para identificar contas automatizadas, atribuindo um grau de probabilidade de a conta ser um bot, com foco em economizar tempo do usuário e evitar interações sem relevância.

---

## 🗺️ Roadmap do Projeto (CBL)

| Fase | Foco | Período |
|---|---|---|
| **Semana 1: ENGAGE** | Entender o desafio | *Ativo* |
| **Semanas 2-3: INVESTIGATE** | Pesquisa e descoberta de viabilidade técnica | *Em breve* |
| **Semanas 4-5: ACT** | Desenvolvimento do protótipo e solução | *Em breve* |
| **Semana 6: SHOWCASE** | Partilha de conhecimento | *Em breve* |

---

## 📦 Entregáveis Finais
Ao final do ciclo de 6 semanas, este repositório abrigará:
- [ ] Portfólio de pesquisa
- [ ] Estrutura de avaliação de confiança
- [ ] Solução/protótipo com suporte de IA
- [ ] Apresentação e reflexão

## 🏗️ Estrutura do repositório

```
ContrarIA/
├── api/        # FastAPI + worker do pipeline (coleta → triagem → bot score → verificação → intervenção)
├── research/   # datasets, treino do pré-filtro de fake news e benchmarks
├── deploy/     # produção: Caddy (HTTPS) + Ozone (labeler)
├── web/        # painel React (pós-MVP)
└── docs/       # site MkDocs: planejamento, arquitetura, ADRs, atas
```

Detalhes e o porquê de cada camada: [`docs/arquitetura/index.md`](docs/arquitetura/index.md).

## 🚀 Rodando localmente

### Pré-requisitos e Hardware

- **Software:** Docker Engine 24+ com Docker Compose v2, e [uv](https://docs.astral.sh/uv/) (Python 3.12+).
- **Hardware Mínimo (para rodar a aplicação):** 8 GB de RAM na máquina (ao menos 5 a 6 GB alocados ao Docker), 4 núcleos de CPU e 15 GB livres em disco.
- **Hardware Recomendado (para rodar com folga):** 16 GB de RAM na máquina (8 a 10 GB no Docker), 8 núcleos de CPU e 30 GB livres em SSD.
- **Consumo real em regime contínuo:** A pilha completa (`db`, `jev`, `searxng`, `api`, `worker`) consome em torno de **~3,3 GiB a 4,5 GiB de RAM** graças à eficiência do modelo Cross-Encoder NLI `mDeBERTa-v3` (~500 MB de peso) e ao SearXNG enxuto (~280 MiB).

```bash
make setup   # cria api/.env a partir do .env.example e instala dependências
make up      # sobe db (Postgres + pgvector), jev, searxng, api e worker
curl http://localhost:8000/health   # {"status":"ok"}
```

Swagger em http://localhost:8000/docs. Outros alvos: `make lint`, `make test`, `make logs`, `make docs-serve`.

### Verificação local com Jev

O backend operacional é o **Jev**: um classificador discriminativo local baseado no modelo **mDeBERTa-v3** NLI (`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`). Em vez de um LLM gerativo pesado forçado por logprobs, ele atua como um Cross-Encoder especializado em Inferência de Linguagem Natural (premissa vs hipótese) com classe neutra nativa (*neutral*), eliminando falsos positivos onde a ausência de evidência era tratada como desmentido. O worker separa as frases factuais, consulta as fontes de evidência (incluindo o metabuscador local SearXNG com Trafilatura), filtra os resultados relevantes e pede ao Jev o veredito NLI. O modelo roda uma única vez no serviço `jev`, compartilhado pela API e pelo worker, consumindo apenas ~500 MB a 1 GB de RAM e respondendo em ~50-80ms por par em CPU.

O CRC mantém uma calibração própria para a combinação de modelo e arquivo do
Jev; sem essa calibração o sistema se abstém e não publica. O LLM configurado
continua sendo usado somente depois de uma decisão elegível, para redigir o
texto socrático do quote post com base nas evidências reunidas. Veja a
[arquitetura](docs/arquitetura/index.md), o
[pipeline](docs/arquitetura/pipeline.md) e o
[guia de calibração](docs/calibracao-jev.md).

### Backend alternativo de LLM

`ClaimVerificationPlanner` classifica trechos do post, do conteúdo citado e do pai como
fato, opinião, sátira/ironia, hipérbole ou pergunta. Conteúdo sem alegação factual encerra
o fluxo; fatos recebem perguntas independentes de verificação, sem respostas ou veredito.
Os prompts ficam versionados em `api/app/prompts/` e toda saída do modelo passa por
validação Pydantic antes de chegar ao pipeline.

As perguntas CoVe são processadas isoladamente pelo `SelfRAGService`: as fontes habilitadas
são consultadas em paralelo, evidências irrelevantes são descartadas e somente respostas
sustentadas seguem no fluxo. As reflexões `[Retrieve]`, `[IsRel]`, `[IsSup]` e `[IsUse]` ficam
disponíveis em `agent_outputs` para auditoria e para as etapas de debate e veredito.

Esse caminho permanece disponível com `VERIFICATION_BACKEND=llm`, mas não é o
backend padrão da operação com Jev.

O conjunto dourado pode ser validado com um modelo real configurado no `.env`:

```bash
cd api
uv run python -m scripts.validate_claim_extraction \
  --cases ../research/claim_extraction_golden.json \
  --output ../research/claim_extraction_validation.json
```

## 🗂️ Planejamento, documentação e atas

- Board: GitHub Project do ContrarIA, com a lógica explicada em [`docs/planejamento.md`](docs/planejamento.md).
- Documentação completa (MkDocs): `make docs-serve`, fonte em [`docs/`](docs/).
- Atas das reuniões: [`docs/atas`](docs/atas/).

## 🌿 Branches e PRs

- `main` sempre estável: todo trabalho entra por PR, revisado pela outra pessoa da dupla.
- `feature/<descrição-curta>`: uma branch por issue, com `Closes #N` no PR.
- O CI (ruff + pytest + build do MkDocs) roda em todo PR.

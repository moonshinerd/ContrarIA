# Como funciona o ContrarIA: o pipeline do agente

Este guia explica a arquitetura prevista para o MVP, para o público do showcase. A disponibilidade de cada etapa depende da conclusão e integração das respectivas issues; a documentação não é uma comprovação de execução em produção.

## Visão geral

O ContrarIA acompanha publicações políticas em português no Bluesky, seleciona candidatos, busca evidências e decide se há fundamento para uma intervenção. Quando faltam evidências, ele se abstém. O processo pode ser entendido em cinco etapas:

```mermaid
flowchart LR
    A["1. Coleta"] --> B["2. Triagem e bot score"]
    B --> C["3. Verificação e debate"]
    C --> D["4. Intervenção ou abstenção"]
    D --> E["5. Registro da decisão"]
```

## 1. Coleta: encontrar publicações

O Jetstream fornece eventos de novas publicações. Em paralelo, buscas periódicas com `searchPosts`, ordenadas por `top`, recuperam posts das últimas 24 horas que podem ter circulado antes de o agente iniciar. A coleta filtra idioma português e palavras-chave políticas, evita duplicatas pela URI e guarda um cursor para retomar o fluxo após reiniciar.

É como acompanhar as notícias que chegam e também consultar as que já ganharam atenção.

**Referências:** [RF01](../requisitos.md), [ADR 0009](../adr/0009-coleta-hibrida-jetstream-searchposts.md).

## 2. Triagem: escolher o que investigar

O sistema avalia tema, relevância, velocidade de propagação e sinais de automação da conta. O bot score combina características como frequência, regularidade, repetição de texto e perfil em uma nota entre 0 e 1. Uma nota alta é um indício, não prova de automação; os pesos e limiares precisam ser avaliados.

Um classificador clássico opcional fornece outro sinal para priorizar candidatos com provável desinformação. Ele nunca decide sozinho publicar ou rotular. Candidatos com baixa prioridade podem continuar em monitoramento.

É como organizar uma fila de investigação: prioridade não é condenação.

**Referências:** [RF02, RF04, RF08, RF09, RF10 e RF12](../requisitos.md), [ADR 0006](../adr/0006-bot-score-heuristico.md), [ADR 0008](../adr/0008-pre-filtro-classico.md).

## 3. Verificação: confrontar a alegação com evidências

1. **Entender o texto:** separar alegações verificáveis de opinião, sátira, ironia, hipérbole e perguntas. Conteúdo não factual encerra sem ação.
2. **Fazer perguntas independentes (CoVe):** dividir a alegação em pontos que possam ser checados, sem copiar o viés da resposta inicial.
3. **Buscar e avaliar evidências (Self-RAG):** consultar as fontes habilitadas, como agências de checagem, Wikipédia, busca web e acervo de RSS. Descartar material irrelevante e manter respostas sustentadas, considerando a data das informações.
4. **Debater com três papéis:** o Promotor apresenta a acusação, o Defensor procura falhas e contraprovas, e o Juiz avalia os argumentos e as fontes. O Juiz também avalia explicitamente se sabe o suficiente para decidir, sinal chamado P(IK).
5. **Aplicar o controle de risco:** o Conformal Risk Control (CRC) usa um limiar aprendido com exemplos rotulados, separado dos dados de teste, com tolerância de 5% para a perda de falsos positivos na calibração. Não é uma regra fixa de 80% de confiança nem garantia de acerto em todos os casos. Confiança abaixo do limiar, P(IK) baixo ou falta de consenso levam à abstenção (`INSUFFICIENT_EVIDENCE`).

É como uma análise pericial que ouve a acusação e a defesa e admite quando não consegue concluir.

**Referência:** [ADR 0007 — verificação, debate e CRC](../adr/0007-verificacao-cove-selfrag-mad-crc.md).

## 4. Ação: intervir somente quando houver fundamento

Após a análise completa, um veredito falso ou enganoso elegível pode gerar um **quote post no perfil do bot**, citando a publicação e uma fonte. Para humanos prováveis, o tom é empático e socrático; para bots prováveis, é clínico e descreve sinais de automação. Não há reply nem menção direta ao autor.

Quote posts notificam o autor. A decisão aceita o risco relacionado à diretriz de opt-in descrito no ADR 0002; a citação não elimina esse risco. Limites por post, autor e dia, orçamento, anti-loop e postgate restringem a publicação. Se o autor bloqueou citações, o sistema não publica o quote post.

A rotulagem pelo **Ozone** é complementar, por uma conta dedicada de labeler: `possivel-desinformacao` em conteúdo e `provavel-bot` em conta, conforme a análise. Usuários que assinam esse serviço podem ver os rótulos; uma revisão do veredito pode negá-los, sem apagar o histórico. O score sozinho não autoriza rotulagem.

Conteúdo verdadeiro ou não factual não recebe intervenção corretiva. Um resultado inconclusivo causa abstenção, sem ação penalizadora.

**Referências:** [RF05, RF06 e RF07](../requisitos.md), [ADR 0002](../adr/0002-quote-post.md), [ADR 0003](../adr/0003-labeler-ozone.md).

## 5. Auditoria: registrar o motivo da decisão

A decisão, inclusive monitoramento ou abstenção, deve ser registrada com os dados necessários para explicar seu resultado: publicação, data, bot score, evidências, reflexões, debate, limiar usado e ação tomada. Isso permite revisar os motivos e corrigir decisões posteriores sem perder o histórico.

É o registro que permite ao avaliador conferir como a conclusão foi construída.

**Referências:** [RF13 e RNF06](../requisitos.md), [visão geral da arquitetura](index.md).

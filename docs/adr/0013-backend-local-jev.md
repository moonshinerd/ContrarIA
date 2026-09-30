# 0013 — Backend de Verificação Local Jev

- **Status:** Aceita
- **Data:** 28/09/2026
- **Requisitos / GQs:** RF03, RNF01, RNF05
- **Origem:** PR [#57](https://github.com/moonshinerd/ContrarIA/pull/57)

## Contexto

O fluxo completo de CoVe, Self-RAG e debate por LLM remoto exigia muitas
chamadas por post, tinha custo variável e era sensível a respostas JSON fora do
formato. Para a operação contínua do bot, precisávamos de uma decisão local,
reprodutível e com um controle de risco que não confundisse a confiança de
modelos diferentes.

## Decisão

Adotar Jev como backend operacional de verificação (`VERIFICATION_BACKEND=jev`).
O Jev utiliza o modelo discriminativo Cross-Encoder NLI `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (substituindo o protótipo inicial Qwen3-4B GGUF). Ele avalia a relação lógica direta entre premissa e hipótese com suporte nativo à classe neutra (*neutral*), sem gerar JSON e sem alucinações. Para cada frase factual, ele busca fontes, filtra a relevância e escolhe entre confirmação, desmentido ou enganosidade.

O modelo é servido pelo contêiner `jev` e compartilhado por API, worker e
scripts via HTTP. A confiança passa por CRC com chave exclusiva
`jev:<repositório>`; sem calibração ou abaixo do limiar, o resultado
é `insufficient_evidence`. O LLM remoto continua no sistema apenas para
redigir o texto socrático de uma intervenção que já foi considerada elegível.

## Alternativas consideradas

- **Modelos Gerativos Autorregressivos (Qwen3-4B GGUF via llama.cpp):** Testados no início do Jev, mas descartados devido ao maior consumo de RAM (~3,5 GB), dependência de compilação C++ e ausência de classe neutra nativa (o que induzia ausência de evidência a ser classificada como desmentido).
- **Manter o LLM remoto como único backend:** preserva o debate, mas mantém
  custo por chamada e fragilidade no formato estruturado.
- **Carregar Jev em API e worker:** descartado porque as cópias do modelo
  duplicariam a memória disponível desnecessariamente.
- **Usar Jev sem CRC:** descartado; uma confiança não calibrada não autoriza
  publicação automática.

## Consequências

- A decisão factual deixa de depender de geração JSON e de múltiplas chamadas
  remotas, mas exige CPU e memória local.
- Cada troca de repositório ou arquivo GGUF exige nova calibração CRC.
- O serviço processa uma classificação por vez, portanto matérias longas podem
  aumentar a latência da fila.
- CoVe/Self-RAG/debate seguem disponíveis para comparação e contingência com
  `VERIFICATION_BACKEND=llm`; os limiares de CRC não são intercambiáveis.

# 0007 — Verificação com CoVe, Self-RAG, Debate Multiagente e Conformal Risk Control

- **Status:** Aceita — fluxo alternativo; backend operacional substituído pelo ADR 0013
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF03, RF15, RF16, RNF01, GQ02, GQ03
- **Origem:** [#22](https://github.com/moonshinerd/ContrarIA/issues/22), [#23](https://github.com/moonshinerd/ContrarIA/issues/23), [#24](https://github.com/moonshinerd/ContrarIA/issues/24), [#25](https://github.com/moonshinerd/ContrarIA/issues/25)

## Contexto
Uma única resposta de LLM pode reproduzir informação desatualizada, ignorar sátira ou confirmar o viés da alegação. O MVP precisa cruzar evidências e se abster quando não dispõe de suporte suficiente. Confiança declarada pelo modelo não equivale a uma garantia de verdade.

Este ADR registra o fluxo originalmente adotado para o backend LLM. Desde
28/09/2026, a operação padrão usa a verificação Jev descrita no
[ADR 0013](0013-backend-local-jev.md). Este fluxo continua disponível quando
`VERIFICATION_BACKEND=llm`, e sua calibração CRC permanece separada da
calibração do Jev.

## Decisão
Compor as seguintes etapas em `VerificationService.verify(post)`:

1. **Extração e CoVe:** distinguir alegações factuais de opinião, sátira, ironia, hipérbole e perguntas. Conteúdo não factual encerra sem ação. Na variante factored, cada pergunta de verificação é respondida isoladamente; a data atual orienta a análise temporal.
2. **Self-RAG:** emular reflexão com passos de crítica em JSON, sem pressupor fine-tuning. Usar `[Retrieve]`, `[IsRel]`, `[IsSup]` e `[IsUse]`, consultar as fontes habilitadas em paralelo e manter respostas sustentadas por evidências. Evidência recente e confiável prevalece sobre memória do modelo.
3. **Debate:** o **Promotor** sustenta a acusação com evidências; o **Defensor** procura contraprovas, contexto e sátira; o **Juiz** decide após as rodadas (padrão: duas, configurável). O resultado inclui rótulo, confiança, justificativa, evidências citadas e consenso. Modelos por papel são configuráveis.
4. **Humildade epistêmica P(IK):** adotar a avaliação explícita do Juiz sobre a probabilidade de conhecer suficientemente a resposta, como pergunta distinta da classificação factual, em vez de estimá-la pela concordância de k amostras. P(IK) e confiança são sinais distintos; P(IK) baixo ou oposição sem consenso estável sinalizam abstenção.
5. **Conformal Risk Control (CRC) em runtime:** calibrar o limiar λ̂ com alegações rotuladas, em conjunto disjunto do teste do benchmark. A perda é o falso positivo (alegação verdadeira classificada como falsa), com tolerância α = 0,05 e B = 1. Escolher o menor λ que satisfaça `(n/(n+1)) · R̂ₙ(λ) + B/(n+1) ≤ α` e persistir `lambda`, `alpha`, `n`, modelo e data em `crc_calibration`. Não se trata de um algoritmo de consenso nem de um limiar fixo de 80%.

Em runtime, `confidence < λ̂`, P(IK) baixo **ou** ausência de consenso resultam em `INSUFFICIENT_EVIDENCE`, sem ação penalizadora. O veredito completo inclui evidências, reflexões, transcrição do debate e o limiar usado para auditoria.

## Alternativas consideradas
- **Prompt único com RAG:** não fornece debate e controle explícito de risco.
- **Limiar fixo de confiança:** não incorpora a calibração empírica exigida na issue #25.
- **Autoconsistência com k amostras para P(IK):** alternativa prevista na issue #24, não escolhida aqui por exigir chamadas adicionais.
- **Fine-tuning para os tokens de Self-RAG:** fora do escopo; a crítica estruturada permite utilizar modelos via API.

## Consequências
- Abstenção e calibração ajudam a controlar falsos positivos; não garantem evidência incontestável nem erro zero em qualquer distribuição.
- Mudanças de modelo ou distribuição exigem atenção à validade da calibração.
- Reflexões, debate e limiar precisam ser auditáveis; chamadas, perguntas e evidências têm limites para respeitar o orçamento.
- A verificação custa mais e tem maior latência que uma chamada única.

# 0007 — Pipeline de Verificação com CoVe, Self-RAG e Debate Multiagente (MAD/CRC)

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF03, RF15, RF16, RNF01, GQ02, GQ03, Issues #22, #23, #24, #25

## Contexto
Submeter uma alegação complexa a uma única chamada de modelo de linguagem generativo com um prompt direto (ex.: *"Isto é verdadeiro ou falso?"*) apresenta fragilidades graves:
1. Alucinações frequentes quando o modelo confia em memórias paramétricas desatualizadas.
2. Vieses de confirmação (*confirmation bias*) induzidos pelo tom da postagem analisada.
3. Ausência de calibração matemática de incerteza, induzindo o agente a emitir julgamentos categóricos mesmo diante de evidências escassas (elevando o risco de falsos positivos).

## Decisão
Implementar uma arquitetura de verificação em quatro etapas sequenciais no serviço de inteligência:
1. **Extração de Fatos e CoVe (Chain of Verification)**: Decomposição da alegação em perguntas pontuais de checagem, executadas de forma independente para evitar contaminação do raciocínio (Issue #22).
2. **Self-RAG (Self-Reflective Retrieval-Augmented Generation)**: Consulta a fontes externas com tokens de autocrítica que avaliam se os documentos recuperados são realmente úteis e suficientes (Issue #23).
3. **Debate Multiagente (MAD - Multi-Agent Debate)**: Dois agentes com personas distintas (um Agente Analista com foco nas evidências e um Agente Cético atuando como advogado do diabo) confrontam argumentos sobre a alegação (Issue #24).
4. **CRC (Confidence-calibrated Robust Consensus)**: Algoritmo de consenso que calcula uma probabilidade calibrada de verdade. Se a confiança calculada for inferior a 80%, o sistema aciona a **Abstenção Mandatória** (Issue #25).

## Alternativas consideradas
- **Prompt Único com RAG Convencional**: Descartado por não possuir mecanismo de contra-argumentação nem autocrítica das fontes recuperadas.
- **Fine-Tuning de Modelo Proprietário**: Descartado pelo custo de anotação de dados e pela incapacidade de incorporar fatos noticiosos que ocorrem após o término do treinamento.

## Consequências
- **Positivas**:
  - Minimização drástica de falsos positivos (RNF01), garantindo que o agente só intervenha quando houver evidência incontestável.
  - Rastreabilidade argumentativa completa (RNF06): o laudo registra a cadeia de perguntas do CoVe e as rodadas do debate.
  - Capacidade de lidar com sátiras e ironias (RF15) por meio do escrutínio do agente cético.
- **Negativas / Riscos assumidos**:
  - Maior latência no processamento de cada postagem (múltiplas chamadas consecutivas de inferência).
  - Maior consumo de tokens de API por verificação concluída.

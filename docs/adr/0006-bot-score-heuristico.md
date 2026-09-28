# 0006 — Detecção de Contas Automatizadas via Bot Score Heurístico Ponderado

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF02, RF12, RNF05, GQ02, Issue #13

## Contexto
Para adaptar a estratégia de intervenção (RF06) e direcionar ações aos alvos corretos (diálogo socrático para humanos vs. rotulagem Ozone para bots), o sistema precisa estimar a probabilidade de uma conta do Bluesky ser automatizada.
No entanto, essa análise ocorre na fase de triagem, onde o volume de publicações recebidas por segundo é muito alto. Submeter cada conta a uma rede neural profunda de análise de grafo ou invocar um modelo de linguagem para ler centenas de postagens antigas é computacionalmente e financeiramente inviável.

## Decisão
Implementar um módulo de **Bot Score Heurístico Ponderado**. O algoritmo calcula um escore normalizado entre `0.0` e `1.0` combinando métricas comportamentais e cadastrais extraídas diretamente dos metadados da API do Bluesky:
1. **Frequência de Postagem**: Taxa de publicações por hora e atividade ininterrupta durante 24 horas.
2. **Regularidade Temporal**: Variância matemática reduzida dos intervalos entre postagens (indicativo de disparos cronometrados).
3. **Repetição de Conteúdo**: Taxa de duplicidade ou similaridade em postagens consecutivas.
4. **Métricas de Perfil**: Razão entre seguidores e seguindo (*follow ratio*), ausência de foto de perfil (avatar padrão) e idade da conta.

## Alternativas consideradas
- **Classificador Neural Pesado (Deep Learning)**: Descartado por exigir infraestrutura de GPU em produção e latência incompatível com o stream em tempo real.
- **Uso de Serviços Externos Fechados (ex.: Botometer)**: Descartado por ser restrito ao Twitter/X e não possuir integração com o AT Protocol.

## Consequências
- **Positivas**:
  - Execução ultrarrápida (na casa dos microssegundos) em memória RAM, sem consumir cotas de LLM (RNF05).
  - Explicabilidade total (RNF06): o log do sistema pode detalhar exatamente quais regras elevaram a pontuação da conta.
  - Facilidade de calibração: os pesos dos fatores podem ser ajustados com base nos testes de benchmark da Issue #18.
- **Negativas / Riscos assumidos**:
  - Menor sensibilidade contra redes de desinformação híbridas (*cyborgs*), onde operadores humanos intercalam ações com automações.

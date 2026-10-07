# 0022 — Janela de maturação e critic semântico

- **Status:** Aceita
- **Data:** 07/10/2026
- **Requisitos / GQs:** RNF01, RF03, RF05, GQ03

## Contexto
A investigação dos posts publicados desde 05/10/2026 mostrou três falhas recorrentes: (1) posts analisados minutos
depois de publicados, antes de a notícia existir ou ser indexada, davam veredito errado ou desatualizado; (2) o texto
do quote respondia à **reportagem** e não ao **post**, atribuindo ao autor pessoas ou dados que ele não citou (caso do
post sobre o ES que ganhou uma resposta sobre Nikolas Ferreira); (3) o classificador local, sem opção de abstenção,
colapsava evidência que não tratava da alegação para `false`.

## Decisão
- **Janela de maturação (aging delay).** `get_triage_candidates` só entrega posts com idade entre `POST_MIN_AGE_HOURS`
  (3 h) e `POST_MAX_AGE_HOURS` (48 h). O worker expira os posts acima do limite ao iniciar e a cada rodada de intervenção.
- **Critic semântico.** Depois de redigido, o quote passa por uma auditoria por LLM (`semantic_critic_v1.txt`, em
  `InterventionService._validate_semantic_coherence`, ligada por `ENABLE_SEMANTIC_CRITIC`) que veta o texto se a
  pergunta não fizer sentido com o **post**, ou se imputar ao autor personagens, declarações, leis ou dados ausentes
  dele. O prompt de redação (`quote_post_v2.txt`) passa a tratar a reportagem como fonte de evidência e o post como
  único destinatário.
- **Abstenção no classificador.** O Jev ganhou a opção "as evidências são insuficientes ou não tratam da alegação",
  mapeada para `insufficient_evidence`.
- A solução é **semântica**, não de expressões regulares: a guarda determinística de entidades continua como primeira
  barreira, e o critic cobre os casos que ela não enxerga.

## Alternativas consideradas
- **Janela de 24 h:** descartada; boa parte das checagens e matérias chega depois.
- **Só regras determinísticas (regex) contra alucinação:** engessam e regridem com cada caso novo.
- **Sem aging:** mantém a análise em tempo real, ao custo de vereditos sobre notícias ainda inexistentes.

## Consequências
- Uma chamada de LLM a mais por candidato que chega à publicação (orçamento `DAILY_LLM_BUDGET_USD`).
- Posts muito recentes esperam 3 h; o que esfria além de 48 h expira sem análise.
- O critic é um segundo modelo opinando sobre o primeiro: reduz, mas não elimina, quotes fora de contexto.

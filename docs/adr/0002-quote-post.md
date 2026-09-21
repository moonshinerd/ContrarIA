# 0002 — Intervenção por Quote Post em vez de Resposta no Fio ou Menção Direta

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF05, RF06, RF14, RNF03, RNF04, GQ01, GQ07

## Contexto
A forma como um agente autônomo interage nas redes sociais determina sua aceitação comunitária e eficácia contra a desinformação. O projeto precisava resolver dois dilemas fundamentais de interação:
1. **Risco de Spam e Rejeição**: A comunidade do Bluesky valoriza diretrizes de *opt-in* e rejeita veementemente bots que poluem tópicos de discussão alheios com respostas intrusivas (*replies* não solicitadas).
2. **Efeito Backfire Psicológico**: A literatura científica comprova que confrontar diretamente um usuário radicalizado no seu próprio fio tende a aumentar a sua resistência cognitiva e gerar polarização defensiva.

## Decisão
A intervenção pública do ContrarIA ocorrerá exclusivamente através de **Quote Post** (postagem no perfil do próprio bot citando a publicação analisada). O agente **nunca responderá diretamente no fio da postagem original** (*reply*) e **não marcará o autor original via menção (@)**.

## Alternativas consideradas
- **Resposta Direta no Fio (*Reply*)**: Descartada por violar a expectativa de moderação e privacidade do autor do post, elevando o risco de denúncias em massa por spam e bloqueio do bot.
- **Menção Direta com @**: Descartada porque notificações invasivas provocam reações beligerantes e facilitam que redes de bots adversários coordenem ataques de negação de serviço contra o agente.
- **Mensagem Direta Privada (DM)**: Descartada porque anularia o benefício educativo para a audiência observadora (*bystanders*).

## Consequências
- **Positivas**:
  - Respeito integral às normas comunitárias e termos de uso do Bluesky (RNF03).
  - O agente comunica-se prioritariamente com a audiência espectadora (*bystanders*), que possui maior propensão a absorver a checagem factual reflexiva.
  - Imunidade a loops recursivos de réplicas e ataques de spam orquestrados em tópicos de comentários.
- **Negativas / Riscos assumidos**:
  - O autor original da postagem desinformativa pode não tomar conhecimento imediato da checagem reflexiva, a menos que visualize as citações ao seu post.

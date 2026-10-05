# 0017 — Rotulagem de contas com `provavel-bot` ao vivo

- **Status:** Aceita (ajusta o [ADR 0003](0003-labeler-ozone.md) e o RF07)
- **Data:** 05/10/2026
- **Requisitos / GQs:** RF02, RF07, RF12, RNF01, GQ07

## Contexto
O [ADR 0006](0006-bot-score-heuristico.md) criou o bot score para direcionar a ação: diálogo socrático para humanos e
rotulagem pelo Ozone para bots. Na prática, o código só rotulava o **post** com `possivel-desinformacao`, depois de um
quote publicado, e o rótulo `provavel-bot` nunca foi emitido. O RF07 condicionava a sinalização à "conclusão do
processo de análise e interação", o que deixava a maioria das contas analisadas sem sinalização.

## Decisão
Rotular **todas as contas que o pipeline analisa**, com `provavel-bot`, sem depender de quote post. A decisão é por
operação ao vivo, sem fase em modo sombra: a calibração do limiar acontece com o tempo, em produção.

`AccountLabelService` (`app/services/account_labeling.py`) roda a cada análise, logo após o bot score:

- **Emite** `provavel-bot` quando `score ≥ ACCOUNT_LABEL_THRESHOLD` (padrão 0,9) e a conta tem ao menos
  `ACCOUNT_LABEL_MIN_POSTS` posts (padrão 20).
- **Nega** o rótulo quando o score cai abaixo de `limiar − ACCOUNT_LABEL_HYSTERESIS` (padrão 0,1), sem apagar o
  histórico. A histerese evita que uma conta perto do limiar ganhe e perca o rótulo a cada reavaliação.
- **Registra o estado** em `account_assessments.bot_label_applied` (migration `b3a1c9d4e7f2`), então não emite de novo
  a cada análise. O estado só muda depois de a emissão dar certo; uma falha do Ozone vira log e é tentada na análise seguinte.
- Segue controlada por `PIPELINE_LABELER_ENABLED` (padrão `false`): é uma ação pública e continua opt-in.

O rótulo é informativo (`severity: inform`, sem borrar conteúdo) e só aparece para quem assina o labeler.

## Alternativas consideradas
- **Modo sombra antes de emitir:** recomendado para medir a precisão real, mas descartado pela equipe em favor de
  calibrar ao vivo.
- **Rotular só contas que receberam quote post:** mantém o RF07 original, mas deixa quase todas as contas sem sinalização.

## Consequências
- Cada conta com score alto passa a ser sinalizada publicamente. Um falso positivo é um dano real a uma pessoa real,
  em tensão com o RNF01. O limiar de 0,9 e o mínimo de posts são pontos de partida.
- Os números de avaliação do bot score (ROC-AUC 0,999, precisão 0,998 no limiar 0,9) vêm de uma regressão com
  características diferentes das do `bot_weights.yaml` em produção e de um dataset não validado para contas políticas
  do Bluesky. Não são garantia de precisão para este uso.
- Medir a precisão real exige revisar amostras de contas rotuladas. Contestações devem ser atendidas negando o rótulo.
- Cada rótulo é uma chamada ao Ozone; o estado persistido mantém o volume proporcional às mudanças, não às análises.

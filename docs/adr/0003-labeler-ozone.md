# 0003 — Uso do Servidor Oficial Ozone para Rotulagem Descentralizada

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF07, RNF03, RNF07, GQ07

## Contexto
Além da intervenção pedagógica textual via Quote Post, o desafio exige mecanismos formais de sinalização técnica de contas automatizadas e conteúdos desinformativos. O protocolo AT Protocol introduziu o conceito de **Labelers independentes**: serviços federados que emitem etiquetas criptograficamente assinadas para perfis e publicações, permitindo que os usuários escolham quais provedores de moderação desejam seguir no aplicativo oficial.

## Decisão
Fazer o deploy e manter uma instância oficial do **Ozone** (software de moderação do Bluesky/Skyware), configurando a conta do ContrarIA como um *Labeler* oficial da rede. O serviço emitirá rótulos padronizados (ex.: `bot-score-high`, `desinformacao-eleitoral`) que aparecem diretamente na interface do aplicativo para os usuários que subscreverem o serviço.

## Alternativas consideradas
- **Armazenamento de Rótulos em Banco Proprietário**: Descartado porque os rótulos ficariam confinados ao banco de dados interno da aplicação, sem qualquer visibilidade ou utilidade direta para os usuários do Bluesky.
- **Sinalização Apenas por Texto nos Posts**: Descartada por não permitir aos usuários configurarem preferências de ocultação ou advertência automática na interface do cliente AT Protocol.

## Consequências
- **Positivas**:
  - O projeto ContrarIA atua como uma autoridade de moderação descentralizada nativa e auditável.
  - Conformidade perfeita com o ecossistema e com os requisitos RF07 e RNF07.
  - Usuários do Bluesky podem voluntariamente assinar o serviço de moderação do ContrarIA para filtrar seu feed.
- **Negativas / Riscos assumidos**:
  - Exige a administração de um serviço contínuo adicional em infraestrutura de produção (VPS dedicada com proxy reverso e certificados TLS).

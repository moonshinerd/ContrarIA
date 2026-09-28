# 0002 — Intervenção por Quote Post em vez de Resposta no Fio ou Menção Direta

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF05, RF06, RF14, RNF03, RNF04, GQ01, GQ07
- **Origem:** [Issue #14](https://github.com/moonshinerd/ContrarIA/issues/14)

## Contexto
A intervenção deve apresentar evidências aos espectadores da conversa sem iniciar um diálogo automático no fio do autor. A escolha precisa registrar o risco de interação não solicitada, e não presumir que uma citação elimina esse risco.

## Decisão
Publicar **quote posts no perfil do bot**, sem replies nem menções ao autor. O tom será empático e socrático para humanos prováveis e clínico, descrevendo os sinais de automação, para bots prováveis. A publicação cita a alegação falsa ou enganosa e inclui um link de evidência, respeitando o limite de 300 grafemas.

**Risco aceito:** conforme registrado na issue #14, a diretriz de bots do Bluesky condiciona interações ao usuário ter marcado o bot. Quote posts notificam o autor e permanecem nessa zona cinzenta de opt-in. A decisão não garante conformidade integral nem elimina denúncias ou bloqueios.

O probing conversacional da GQ07 fica fora do MVP, pois depende de diálogo, incompatível com a escolha de não responder no fio.

## Alternativas consideradas
- **Reply ou menção direta:** descartados para evitar intervenções no fio e conversas automáticas com o autor.
- **Mensagem privada:** descartada por não alcançar os espectadores.
- **Probing conversacional:** adiado por exigir trocas sucessivas com o usuário.

## Consequências
- A checagem fica visível no perfil do bot e prioriza os espectadores.
- Quote posts continuam sujeitos ao risco de opt-in descrito acima; não há imunidade a loops ou spam.
- Guardrails limitam a uma citação por post e uma por autor a cada 24 horas, impedem autocitação e loops com bots que citaram o ContrarIA, e respeitam postgate que proíbe citações. Nesse caso, apenas a rotulagem elegível pode prosseguir.
- O texto deve ser neutro, conter fonte e passar pelas travas de orçamento e intervenções diárias. O dry-run é o padrão fora de produção.

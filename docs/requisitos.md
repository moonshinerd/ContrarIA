# Requisitos do Sistema

Rastreabilidade entre os requisitos do sistema (funcionais e não funcionais), priorização e as respectivas tarefas de implementação no projeto ContrarIA.

---

## Técnica de Levantamento de Requisitos

O processo de engenharia de requisitos do projeto **ContrarIA** adotou uma abordagem orientada a objetivos, estruturada em duas frentes complementares:

1. **Formulação de Guiding Questions (GQ)**: Essenciais para a compreensão do problema central. Cada necessidade foi decomposta em requisitos funcionais (RF) e não funcionais (RNF). A coluna de **Origem** estabelece uma rastreabilidade bidirecional direta: todo requisito implementado é justificado por uma ou mais Guiding Questions, prevenindo requisitos órfãos e desvios de escopo.
2. **Priorização MoSCoW**: Utilizada para gerenciar o escopo do MVP diante de janelas curtas de entrega e restrições de recursos (quotas de LLM, limites de APIs externas):
    - **Must have (Obrigatório)**: Itens essenciais para a viabilidade do MVP (fluxo crítico: coleta, busca de evidências, classificação com abstenção, intervenção socrática, controle de loops adversários e limites da plataforma Bluesky).
    - **Should have (Importante)**: Capacidades fundamentais que agregam eficácia, mas não inviabilizam a operação básica (adaptação humano/bot, repetição de padrões, sátiras e logs imutáveis).
    - **Could have (Desejável)**: Recursos de valor agregado implementados se houver folga operacional (sinalização posterior de posts e etapas extras de revisão).
    - **Won't have (Fora do Escopo Atual)**: Recursos explicitamente postergados para iterações pós-MVP.

---

## Requisitos Funcionais (RF)

| ID | Requisito | Descrição | Priorização (MoSCoW) | Origem | Issue(s) |
|---|---|---|---|---|---|
| **RF01** | Coleta de publicações | O sistema deve coletar publicações da plataforma para processamento e análise. | Must have | GQ04, GQ06 | [#11](https://github.com/moonshinerd/ContrarIA/issues/11) |
| **RF02** | Detecção de contas automatizadas | O sistema deve analisar características da conta e de seu comportamento para estimar a probabilidade de ela ser automatizada. | Must have | GQ02, GQ07 | [#13](https://github.com/moonshinerd/ContrarIA/issues/13), [#18](https://github.com/moonshinerd/ContrarIA/issues/18) |
| **RF03** | Verificação de informações | O sistema deve avaliar as evidências encontradas e classificar a alegação, permitindo indicar quando não houver evidências suficientes. | Must have | GQ03 | [#22](https://github.com/moonshinerd/ContrarIA/issues/22), [#25](https://github.com/moonshinerd/ContrarIA/issues/25) |
| **RF04** | Priorização da intervenção | O sistema deve selecionar quais publicações merecem intervenção considerando alcance, engajamento, probabilidade de desinformação e suspeita de automação. | Must have | GQ01, GQ04 | [#12](https://github.com/moonshinerd/ContrarIA/issues/12), [#17](https://github.com/moonshinerd/ContrarIA/issues/17) |
| **RF05** | Intervenção socrática | O sistema deve publicar uma resposta no fio da publicação-alvo utilizando o método socrático (indagação reflexiva e referência factual neutra), focando na conscientização da audiência espectadora (bystanders). | Must have | GQ01, GQ07 | [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RF06** | Adaptação da estratégia de interação | O sistema deve adaptar sua estratégia de interação de acordo com a probabilidade de a conta ser humana ou automatizada. | Should have | GQ01 | [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RF07** | Sinalização de contas e publicações | O sistema deve sinalizar contas ou publicações identificadas como automatizadas ou desinformativas somente após a conclusão do processo de análise e interação. | Could have | GQ07 | [#16](https://github.com/moonshinerd/ContrarIA/issues/16) |
| **RF08** | Classificação de relevância | O sistema deve classificar a relevância das publicações considerando alcance, engajamento e velocidade de disseminação. | Must have | GQ01, GQ04 | [#12](https://github.com/moonshinerd/ContrarIA/issues/12) |
| **RF09** | Filtragem temática | O sistema deve filtrar as publicações coletadas de acordo com o escopo político definido para o MVP. | Must have | GQ04, GQ06 | [#12](https://github.com/moonshinerd/ContrarIA/issues/12) |
| **RF10** | Monitoramento sem intervenção | O sistema deve permitir monitorar publicações que não atendam aos critérios de intervenção sem respondê-las. | Should have | GQ01, GQ04 | [#12](https://github.com/moonshinerd/ContrarIA/issues/12), [#17](https://github.com/moonshinerd/ContrarIA/issues/17) |
| **RF11** | Consulta de fontes externas | O sistema deve buscar fontes externas para obter evidências relacionadas às alegações analisadas. | Must have | GQ03 | [#20](https://github.com/moonshinerd/ContrarIA/issues/20), [#21](https://github.com/moonshinerd/ContrarIA/issues/21), [#23](https://github.com/moonshinerd/ContrarIA/issues/23) |
| **RF12** | Análise de padrões de atividade e repetição | O sistema deve analisar a frequência, os horários e os intervalos entre postagens, além de identificar conteúdos duplicados ou muito semelhantes publicados em curto período, para detectar comportamento automatizado ou anormal. | Should have | GQ02 | [#13](https://github.com/moonshinerd/ContrarIA/issues/13) |
| **RF13** | Registro de decisões | O sistema deve registrar o motivo de cada decisão, incluindo fontes encontradas, score e ação tomada. | Must have | GQ03, GQ04, GQ07 | [#17](https://github.com/moonshinerd/ContrarIA/issues/17) |
| **RF14** | Prevenção de loops e controle de concorrência | O sistema deve impor uma política de réplica única por fio/autor e identificar respostas imediatas de bots adversários para impedir trocas infinitas de mensagens. | Must have | GQ01, GQ05 | [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RF15** | Análise contextual da publicação | O sistema deve considerar o contexto da publicação, incluindo possíveis casos de sátira, ironia ou conteúdo não factual, antes de classificá-la como desinformação. | Should have | GQ03 | [#22](https://github.com/moonshinerd/ContrarIA/issues/22) |
| **RF16** | Revisão da classificação | O sistema deve realizar uma etapa de revisão da classificação preliminar antes de emitir uma classificação conclusiva. | Could have | GQ03 | [#24](https://github.com/moonshinerd/ContrarIA/issues/24) |

---

## Requisitos Não-Funcionais (RNF)

| ID | Requisito | Descrição | Priorização (MoSCoW) | Origem | Issue(s) |
|---|---|---|---|---|---|
| **RNF01** | Confiabilidade da classificação | O sistema deve minimizar falsos positivos e evitar classificações conclusivas quando não houver evidências suficientes. | Must have | GQ03 | [#25](https://github.com/moonshinerd/ContrarIA/issues/25), [#27](https://github.com/moonshinerd/ContrarIA/issues/27) |
| **RNF02** | Atualidade das informações | O sistema deve considerar fontes e informações atualizadas durante a verificação das alegações. | Must have | GQ03 | [#21](https://github.com/moonshinerd/ContrarIA/issues/21), [#23](https://github.com/moonshinerd/ContrarIA/issues/23) |
| **RNF03** | Conformidade com a plataforma | O sistema deve respeitar os limites técnicos, políticas de automação e restrições da plataforma utilizada. | Must have | GQ05 | [#10](https://github.com/moonshinerd/ContrarIA/issues/10), [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RNF04** | Neutralidade das respostas | As respostas geradas pelo sistema devem utilizar linguagem neutra, respeitosa e não agressiva. | Must have | GQ01, GQ07 | [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RNF05** | Controle de custos e recursos | O sistema deve respeitar limites configuráveis de consumo diário de APIs e recursos externos. | Must have | GQ01, GQ05 | [#19](https://github.com/moonshinerd/ContrarIA/issues/19), [#14](https://github.com/moonshinerd/ContrarIA/issues/14) |
| **RNF06** | Rastreabilidade e explicabilidade das decisões | Toda ação do sistema deve gerar um log imutável contendo o post original, bot score, fontes RAG utilizadas, saída dos agentes e justificativa textual da nota de corte. | Should have | GQ05, GQ07 | [#17](https://github.com/moonshinerd/ContrarIA/issues/17), [#13](https://github.com/moonshinerd/ContrarIA/issues/13) |
| **RNF07** | Integração com Bluesky | O sistema deve ser capaz de coletar publicações, analisar contas e publicar respostas na plataforma Bluesky, respeitando as limitações da API escolhida. | Must have | GQ05 | [#10](https://github.com/moonshinerd/ContrarIA/issues/10), [#11](https://github.com/moonshinerd/ContrarIA/issues/11), [#14](https://github.com/moonshinerd/ContrarIA/issues/14), [#16](https://github.com/moonshinerd/ContrarIA/issues/16) |
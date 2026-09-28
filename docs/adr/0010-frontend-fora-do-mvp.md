# 0010 — Postergação de Interface Web (Frontend React) para Pós-MVP

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RF13, Épico #8

## Contexto
O projeto ContrarIA tem como prazo fatal de entrega do protótipo funcional o dia 26 de setembro de 2026 (Semana 6 - Showcase), dispondo de apenas 10 dias úteis para desenvolvimento integrado. 
Na ideação inicial (Semana 1), cogitou-se a construção de um painel administrativo web (*dashboard* em React) com telas de visualização gráfica de contas analisadas, gráficos de redes sociais e relatórios interativos.
No entanto, a equipe possui apenas duas pessoas focadas em infraestrutura e duas pessoas focadas no motor de inteligência artificial, demandando foco absoluto no núcleo que define o sucesso do desafio.

## Decisão
Excluir formalmente o desenvolvimento de qualquer interface gráfica de usuário (frontend React) do escopo do MVP, catalogando a demanda como **pós-MVP no Épico [#8](https://github.com/moonshinerd/ContrarIA/issues/8)**. 
A interação e apresentação do sistema durante o MVP serão realizadas por meio de:
1. Atuação direta na própria interface do aplicativo oficial do Bluesky (Quote Posts e rótulos de moderação Ozone visíveis no perfil).
2. Endpoints REST da API FastAPI para auditoria técnica (`GET /v1/decisions` e `POST /v1/analyze`).
3. Site da documentação técnica construído com MkDocs.

## Alternativas consideradas
- **Construir um Frontend Simplificado/Mínimo**: Descartado porque a manutenção de bibliotecas de frontend, estilização CSS e estado drenaria horas críticas de desenvolvimento de testes de integração da API e do pipeline de verificação.
- **Usar Templates HTML no FastAPI (Jinja2)**: Descartado por adicionar acoplamento no serviço de backend sem entregar uma experiência estética superior à do próprio Bluesky.

## Consequências
- **Positivas**:
  - Concentração total do esforço da engenharia de software na robustez dos contratos de domínio, testes unitários, confiabilidade da IA e benchmarks científicos.
  - Redução drástica da superfície de testes e de manutenção de dependências no contêiner de produção.
- **Negativas / Riscos assumidos**:
  - A demonstração no showcase requer apresentação via terminal/curl ou navegação direta no aplicativo do Bluesky e nas páginas da documentação.

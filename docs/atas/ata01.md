# Ata de Reunião – Alinhamento de Desafio (Fase Engage)

* **Data:** 09 de setembro de 2026
* **Fase Metodológica (CBL):** Semana 1 – *Engage*

* **Tema / Desafio:** *Challenge 1: Fake News / Desinformação*

* **Pergunta Essencial:** *"Como sistemas de IA podem ajudar as pessoas a avaliar a confiabilidade de informações sem substituir seu pensamento crítico?"*


---

## Entregas Finais do Desafio (Semana 6 - Showcase)
De acordo com o documento do desafio, o projeto completo deve contemplar:
- ✓ Portfólio de pesquisa
- ✓ Estrutura de avaliação de confiança
- ✓ Solução/protótipo com suporte de IA
- ✓ Apresentação e reflexão

---

## 1. Contexto e Perfil da Equipe
* **Apresentação e competências:** A equipe conta com perfis multidisciplinares (mecatrônica, hardware/circuitos integrados, desenvolvimento de software, pesquisa em robótica/matemática e gestão/documentação).


* **Definição de papéis preliminares:** Foi destacado o interesse de membros da equipe em liderar a parte de documentação e organização metodológica durante as entregas.



---

## 2. Pautas Discutidas

### 2.1 Análise de Referências e Soluções Existentes

* **ChatGPT (Método Socrático):** Uso de perguntas reflexivas para estimular o raciocínio em vez de fornecer a resposta pronta.


* **Fato ou Fake / Agências de Checagem:** Modelos híbridos onde a IA tria conteúdos suspeitos e humanos realizam a validação final.


* **Notas da Comunidade (X/Twitter):** Sistema baseado em triagem/algoritmos com validação e quórum de humanos com perfis verificados.



---

### 2.2 Propostas de Solução Levantadas (*Brainstorming*)

Foram delineadas **duas frentes principais** de atuação:

1. **Bot Socrático contra Desinformação / *Rage Bait*:**
* Um agente que atua em postagens virais ou comentários com forte indício de desinformação.


* Em vez de impor uma verdade, formula perguntas socráticas para estimular o usuário a questionar a fonte e refletir criticamente.




2. **Detector/Classificador de Bots e Contas Inautênticas:**
* Sistema para identificar perfis automatizados e atribuir um índice/grau de probabilidade de a conta ser um bot (ex.: repetição de texto em múltiplos posts, métricas de engajamento).


* O objetivo inicial era economizar capacidade computacional e evitar interagir/responder a bots sem relevância.




3. **Hipótese de Unificação:**
* A solução final poderia integrar ambos os módulos: triar a autenticidade da conta/postagem e, caso relevante, disparar o questionamento reflexivo/socrático.





---

### 2.3 Desafios Técnicos e Restrições de Viabilidade

* **Teoria da Internet Morta e Ética:** Questionou-se se criar mais bots não acabaria inflando o ecossistema de automações indesejadas.


* **Viabilidade Técnica e Restrições de Plataforma:**
* Não é viável intervir diretamente na interface ou no perfil alheio (ex.: colocar tags/carimbos nas contas de terceiros).


* Limitações de limites de requisição/custo de APIs públicas (como o plano gratuito do X).




* **Arquitetura Aberta vs. Proprietária:**
* Discussão sobre a conveniência de utilizar modelos e APIs *open source* ou locais em contraposição a serviços proprietários fechados, visando autonomia e reprodutibilidade do projeto.





---

## 3. Próximos Passos (Semana 1 - Engage e Transição para Investigate)

Para cumprir as exigências da **Semana 1 (Engage)** estipuladas no desafio, a equipe deve focar nas seguintes entregas e atividades imediatas:

1. **Investigação Forense de Notícias:** Explorar estudos de caso de desinformação (Requisito do desafio).
2. **Workshop da Confiança:** Criar uma matriz de confiança (Requisito do desafio).
3. **Formulação das *Guiding Questions*:** Definir as perguntas orientadoras da pesquisa teórica e técnica.
4. **Exploração de *Datasets* Públicos:** Buscar dados abertos de checagem de fatos e detecção de contas automatizadas para subsidiar a validação científica da solução.

> **Entrega da Semana 1:** Processo investigativo + Guiding Questions.

### 3.1 Planejamento para as Semanas 2 e 3 (Investigate)
* Avaliar a viabilidade de detecção de bots e de análise textual.
* Testar a eficácia e viabilidade do questionamento socrático via IA.
* Comparar a complexidade de implementar os módulos de forma isolada versus uma solução unificada.
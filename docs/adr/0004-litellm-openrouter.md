# 0004 — Abstração de Provedores de LLM com LiteLLM, OpenRouter e Ollama

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RNF05, GQ02, Issue #19

## Contexto
O pipeline de inteligência artificial do ContrarIA executa múltiplas chamadas a modelos de linguagem: extração de alegações factuais, geração de perguntas de validação (CoVe), recuperação crítica (Self-RAG) e debate multiagente. 
Acoplar a base de código diretamente à biblioteca de um único fornecedor (como OpenAI SDK ou Anthropic SDK) introduz:
1. *Vendor lock-in* (dependência de um único fornecedor).
2. Vulnerabilidade a interrupções de serviço (*outages*) ou alterações inesperadas de preço.
3. Custo financeiro cumulativo durante o desenvolvimento e execução de testes automatizados.

## Decisão
Adotar a biblioteca de padronização **LiteLLM** encapsulada sob uma porta de domínio abstrata (`LLMPort`). 
Em produção e integração, o LiteLLM conecta-se ao gateway **OpenRouter**, permitindo rotear requisições dinamicamente para os modelos mais custo-eficientes de diferentes fornecedores. Em ambiente de desenvolvimento local e testes, oferece suporte nativo e sem custos ao **Ollama**.

## Alternativas consideradas
- **SDK Direta da OpenAI**: Descartada pela rigidez de fornecedor único e impossibilidade de executar modelos de pesos abertos localmente em computadores de desenvolvimento.
- **Frameworks de Alto Nível (LangChain / LlamaIndex)**: Descartados por introduzirem camadas excessivas de abstração, dependências pesadas, quebras frequentes de compatibilidade e perda de controle fino sobre os prompts.

## Consequências
- **Positivas**:
  - Capacidade de trocar o modelo subjacente (ex.: de GPT-4o-mini para Claude 3.5 Haiku ou Llama 3) alterando apenas uma variável de ambiente, sem tocar no código Python.
  - Implementação simples de *fakes* e *mocks* nos testes automatizados (`FakeLLM`), garantindo que a suíte de testes de unidade execute em segundos e com custo zero.
  - Controle e monitoramento granular de consumo de tokens para cumprimento do requisito RNF05.
- **Negativas / Riscos assumidos**:
  - Pequenas discrepâncias de aderência ao formato JSON estruturado entre diferentes modelos de LLM quando roteados dinamicamente.

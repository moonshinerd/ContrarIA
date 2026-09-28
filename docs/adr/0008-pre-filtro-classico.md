# 0008 — Pré-filtro Clássico Supervisionado em Datasets PT-BR

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RNF01, RNF05, GQ04
- **Origem:** [Issue #26](https://github.com/moonshinerd/ContrarIA/issues/26)

## Contexto
O pipeline de LLM tem custo por chamada. Um classificador local pode fornecer um sinal barato de provável falsidade para priorizar candidatos, mas os datasets de notícias longas diferem dos posts curtos do Bluesky. Vocabulário e formato podem gerar falsos positivos e negativos.

## Decisão
Avaliar o baseline **TF-IDF + LogisticRegression ou LinearSVC** com **Fake.br, FakeRecogna e Kaggle Fake news in Portuguese**, conforme a issue #26. Fine-tuning de BERTimbau é opcional se houver tempo. Exportar o modelo com joblib, fora do Git, e integrá-lo por `TextClassifierPort`.

O pré-filtro é um **sinal opcional de priorização**, não substitui o filtro temático e não bloqueia a integração. **Nunca decide sozinho uma intervenção:** seu score não constitui evidência factual, não analisa adequadamente contexto e pode sofrer mudança de domínio. Publicações priorizadas ainda passam pela verificação completa e suas regras de abstenção antes de qualquer ação.

Medir F1 no conjunto de teste para texto completo e texto truncado (título + primeiros 300 caracteres), além de avaliar uma amostra manual de posts do Bluesky. Comparar latência e custo por item com uma chamada de LLM.

## Alternativas consideradas
- **LLM para todos os candidatos:** aumenta custo e latência da triagem.
- **Decidir intervenções só com o classificador:** rejeitado por não fornecer a evidência e a confiabilidade exigidas pelo RNF01.
- **BERTimbau:** alternativa opcional; o baseline clássico permite iniciar a comparação com menor custo de treinamento.

## Consequências
- O sinal pode reduzir chamadas de LLM; o ganho precisa ser medido, sem assumir percentuais de redução ou latência ainda não demonstrados.
- Avaliação em textos curtos é necessária antes de extrapolar desempenho medido em notícias longas.
- Pesos, dados e métricas devem permitir reproduzir o benchmark; a verificação factual continua obrigatória para intervir.

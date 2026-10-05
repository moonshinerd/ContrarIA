# Amostra anotada de posts do Bluesky

Amostra de 200 posts reais, tirados da fila de produção em 05/10/2026 e divididos em três arquivos:

| Arquivo | Posts | Responsável |
|---|---|---|
| `amostra_raissa.csv` | 67 | Raissa |
| `amostra_samantha.csv` | 67 | Samantha |
| `amostra_kyara.csv` | 66 | Kyara |

Cada pessoa também tem uma `tabela_<nome>.md`, uma versão só para leitura (o GitHub a renderiza com links clicáveis). O preenchimento é feito no CSV.

**Para que serve.** Hoje não há dado rotulado de posts reais para medir se um sinal de falsidade ou de bot funciona
(a única amostra anotada do projeto tem 20 exemplos; veja o ADR 0015). Esta planilha é a **verdade de referência**:
com ela dá para calcular o AUC de sinais baratos, avaliar o classificador de texto curto e conferir os rótulos do
Ozone (`possivel-desinformacao`, `provavel-bot`, `evidencia-insuficiente`). Ela **não** é a saída do sistema e não
tem nenhum rótulo do Ozone: o labeler está desligado na produção.

## Como anotar

1. Abra o `link_post` de cada post e o `link_perfil` da conta no Bluesky e leia o post inteiro, o contexto (se for resposta ou quote) e o perfil.
2. Pesquise a alegação em fontes de checagem (Lupa, Aos Fatos, g1 Fato ou Fake, Estadão Verifica, Comprova, UOL
   Confere, TSE) e em fontes primárias.
3. **Anote sem olhar o que o ContrarIA decidiu.** Não use o sistema como referência.
4. Preencha duas colunas:

| Coluna | Valores | Quando usar |
|---|---|---|
| `rotulo` | `falso` | A alegação principal é comprovadamente falsa |
| | `enganoso` | Tem base real, mas distorce, omite contexto ou exagera |
| | `verdadeiro` | A alegação principal é comprovadamente verdadeira |
| | `incerto` | Há alegação verificável, mas não dá para concluir com as fontes disponíveis |
| | `sem_alegacao` | Opinião, piada, pergunta, torcida: não há o que checar |
| `conta_parece_bot` | `sim`, `nao`, `incerto` | Perfil com sinais de automação (postagem em massa, texto repetido, sem foto ou bio, conta recém-criada) |

5. Use `observacao` para qualquer dúvida e para a fonte que sustenta o rótulo (um link basta).

## Devolução

Abra um PR com o seu CSV preenchido (só o seu arquivo) ou envie ao Victor. Não altere as colunas nem a ordem das linhas.

## Cuidados

- Os posts são públicos, mas **não republique o texto** fora do projeto e **não contate os autores**.
- Em caso de dúvida real entre `falso` e `enganoso`, prefira `enganoso` e explique na observação.

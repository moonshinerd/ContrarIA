# 0020 — Acesso à VM e deploy por túnel Cloudflare, sem porta de entrada

- **Status:** Aceita (altera a borda HTTPS do ADR 0011)
- **Data:** 05/10/2026
- **Requisitos / GQs:** RNF03, RNF05, RNF07

## Contexto
A VM de produção fica na rede da universidade: não recebe conexões de entrada e o firewall de saída só libera TCP 443
e a porta 7844 (nome local do túnel Cloudflare). Na prática a **7844 também está bloqueada na saída**: o `cloudflared`
da própria VM falha em QUIC e em HTTP/2. O ADR 0011 previa o Caddy emitindo certificado Let's Encrypt, o que exige as
portas 80 e 443 abertas para a internet, e o `deploy.yml` antigo entrava por SSH a partir do runner do GitHub, que não
alcança o IP privado da VM.

## Decisão
- **Túnel `contraria-vm` roda em outra máquina** (o notebook `talos`, que sai pela 7844). A VM publica as portas
  necessárias nele por **SSH reverso**: o serviço `ozone-forward` (systemd, reinicia sozinho) abre uma conexão de saída
  pela 443 usando `cloudflared access ssh` e encaminha `3000` (Ozone) e `8081` (endpoint de deploy) para o loopback do talos.
- O TLS é terminado na Cloudflare. **O Caddy sai do compose de produção**; o Ozone publica `127.0.0.1:3000` na VM.
- Hostnames: `contraria.schmidt.monster` (Ozone, `http://localhost:3000`) e `deploy-contraria.schmidt.monster`
  (endpoint de deploy, `http://localhost:8081`). **O SSH da VM não é publicado.**
- **Chave do túnel restrita:** no talos, a chave da VM só pode abrir esses forwards
  (`restrict,port-forwarding,permitlisten=...,command="/bin/false"`).
- **Deploy por identidade do GitHub, sem SSH:** o `deploy.yml` (só em push na `main`, ambiente `production`) pede ao
  GitHub um token OIDC e o apresenta a um endpoint (`api/app/deployhook.py`) que só aceita este repositório
  (`repository_id`), a branch `main`, o workflow `deploy.yml` e o environment `production`. O endpoint só grava um
  gatilho; um serviço do systemd executa o script de deploy como usuário `deploy`. O container do endpoint não recebe os
  segredos da aplicação, roda sem root e sem acesso ao Docker.
- **Sem Cloudflare Zero Trust/Access.** A autenticação do deploy é a assinatura do GitHub (OIDC); o SSH não é exposto.
- **Disco:** cada deploy limpa camadas órfãs e cache de build antigos, e os logs dos containers têm rotação (sem remover
  volumes). Detalhes em [Operação na VM](../arquitetura/operacao-vm.md#disco-e-cache-do-docker).

## Alternativas descartadas
- **Cloudflare Access com service token:** exige ativar o Zero Trust (cadastro e forma de pagamento) só para proteger um
  hostname; a decisão é não expor o SSH além do necessário e proteger por chave.
- **Runner self-hosted do GitHub na VM:** o repositório é público e um PR de fork poderia executar código na VM.
- **Timer na VM com `git fetch`:** o mais simples e sem nenhuma porta de entrada, mas o deploy atrasa e o resultado não
  aparece no Actions. Segue como alternativa se a infra não aceitar um endpoint público.
- **SSH publicado por túnel com chave de deploy (primeira versão):** funcionou, mas expunha o sshd da VM do laboratório
  à internet; foi substituído pelo endpoint com token OIDC.

## Consequências
- **Dependência do talos:** com ele desligado ou sem rede, Ozone e deploy ficam indisponíveis (a VM segue rodando).
  É aceitável para o MVP; a saída é liberar a 7844 na rede da VM e rodar o `cloudflared` nela.
- O SSH da VM **não** fica na internet: só rede local ou VPN, com senha desligada. Há duas portas públicas: o Ozone
  (necessário para o labeler) e o endpoint de deploy, que recusa tudo que não seja um token do GitHub deste repositório.
  Uma lista de IPs do GitHub Actions foi descartada: são 7.036 faixas, compartilhadas por qualquer conta do GitHub,
  e a VM não enxerga o IP de origem por causa do túnel.
- Segredos de deploy ficam só no ambiente `production` do GitHub e no `api/.env` da VM (permissão 600, fora do git).

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
  pela 443 usando `cloudflared access ssh` e encaminha `3000` (Ozone) e `2223` (SSH da VM) para o loopback do talos.
- O TLS é terminado na Cloudflare. **O Caddy sai do compose de produção**; o Ozone publica `127.0.0.1:3000` na VM.
- Hostnames: `contraria.schmidt.monster` (Ozone, `http://localhost:3000`) e `ssh-contraria.schmidt.monster`
  (`ssh://localhost:2223`).
- **Chave do túnel restrita:** no talos, a chave da VM só pode abrir esses dois forwards
  (`restrict,port-forwarding,permitlisten=...,command="/bin/false"`).
- **Deploy:** o GitHub Actions (`deploy.yml`, só em push na `main`, ambiente `production` restrito à `main`) chega na VM
  com `cloudflared access ssh` e a chave `DEPLOY_SSH_KEY`. No `authorized_keys` do usuário `deploy` essa chave tem
  `command="/opt/contraria-deploy.sh",restrict,no-pty`: só consegue disparar o script de deploy (git reset na `main`,
  `docker compose up -d --build`, `alembic upgrade head`), sem shell. A identidade do servidor é fixada por
  `DEPLOY_HOST_KEY`.
- **Sem Cloudflare Zero Trust/Access.** A proteção do SSH é a chave com comando forçado mais a desativação de senha.

## Alternativas descartadas
- **Cloudflare Access com service token:** exige ativar o Zero Trust (cadastro e forma de pagamento) só para proteger um
  hostname; a decisão é não expor o SSH além do necessário e proteger por chave.
- **Runner self-hosted do GitHub na VM:** o repositório é público e um PR de fork poderia executar código na VM.
- **Timer na VM com `git fetch`:** seguro, mas o deploy atrasa e o resultado não aparece no Actions.

## Consequências
- **Dependência do talos:** com ele desligado ou sem rede, Ozone e deploy ficam indisponíveis (a VM segue rodando).
  É aceitável para o MVP; a saída é liberar a 7844 na rede da VM e rodar o `cloudflared` nela.
- O SSH da VM fica alcançável pela internet via `ssh-contraria`. A defesa é chave única, senha desligada e comando
  forçado; uma regra de IP no WAF (faixas do GitHub Actions) pode reduzir ruído, mas não é identidade.
- Segredos de deploy ficam só no ambiente `production` do GitHub e no `api/.env` da VM (permissão 600, fora do git).

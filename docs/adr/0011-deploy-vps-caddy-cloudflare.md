# 0011 — Infraestrutura de Deploy em VPS com Docker Compose, Caddy e Cloudflare

- **Status:** Aceita
- **Data:** 16/09/2026
- **Requisitos / GQs:** RNF03, RNF05, RNF07, Issue #15

## Contexto
A operação do agente ContrarIA e de seu servidor de moderação Ozone impõe requisitos de infraestrutura específicos:
1. Conexões de rede persistentes de longa duração (WebSockets ininterruptos com o *Jetstream* do Bluesky).
2. Processos de worker em segundo plano (*background loops*) executando de forma ininterrupta.
3. Exposição pública de portas HTTPS com certificados TLS válidos para que a rede federada do AT Protocol reconheça o servidor Ozone como autoridade de moderação.
4. Previsibilidade financeira estrita para não ultrapassar o orçamento do projeto acadêmico.

## Decisão
Hospedar o sistema em um servidor virtual privado dedicado (**VPS Linux Ubuntu**), orquestrado via **Docker Compose**, utilizando o servidor **Caddy** como proxy reverso com emissão automática de certificados HTTPS, integrado à proteção perimetral e DNS da **Cloudflare**.

## Alternativas consideradas
- **Plataformas PaaS Serverless (Vercel / Render Free / AWS Lambda)**: Descartadas porque impõem limites severos de tempo de execução por requisição (*timeout*), desligam instâncias ociosas (*cold starts*) e não suportam conexões WebSocket ativas 24 horas por dia de forma gratuita.
- **Orquestração com Kubernetes (K8s)**: Descartada pela sobrecarga operacional de gerenciamento de cluster, excessiva para a escala de um protótipo com poucos serviços interconectados.

## Consequências
- **Positivas**:
  - Custo operacional mensal fixo e previsível.
  - O Caddy obtém e renova certificados SSL/TLS automaticamente via Let's Encrypt sem necessidade de scripts cron externos.
  - Todo o ambiente (API, Worker, PostgreSQL com pgvector e Ozone) é reprodutível localmente e em produção com um único comando `docker compose up -d`.
  - Proteção perimetral contra ataques distribuídos de negação de serviço (DDoS) via Cloudflare.
- **Negativas / Riscos assumidos**:
  - A equipe é responsável pelo monitoramento e pelas atualizações de segurança do sistema operacional da máquina virtual.

# ADR 001: Infraestrutura de Deploy (VPS + Caddy)

## Contexto

Precisamos fazer o deploy da stack do ContrarIA (API FastAPI, Worker, Postgres, etc) de modo que a infraestrutura seja barata, suporte requisições seguras via HTTPS para integração com features como o Ozone Labeler, e seja de fácil manutenção para o MVP. 

## Decisão

Optamos por utilizar uma VPS Oracle Cloud Free Tier ARM em vez de serviços PaaS (como Heroku ou Render) pelos seguintes motivos:
- Controle completo de recursos e memória usando Docker Compose.
- Possibilidade de configurar o Caddy como gateway unificado para gerenciar automaticamente certificados ACME/Let's Encrypt com ZeroSSL/Cloudflare.
- Restrição explícita de `mem_limit` por container para evitar travamento do host.

A resolução de DNS será feita através da Cloudflare operando no modo "DNS Only" (nuvem cinza), deixando o Caddy providenciar a terminação TLS por conta própria de modo nativo.

## Consequências

- **Positivas:** Custo nulo ou baixíssimo (Free Tier). Deploy direto via Github Actions (`appleboy/ssh-action`).
- **Negativas:** Exige manutenção de sistema operacional da VM (patches, updates de segurança) e gerenciamento de backup do banco de dados (que está rodando na VM ao invés de um RDS gerenciado).

## Pendências operacionais

A instância, o IP público, os registros DNS `api.<domínio>`/`ozone.<domínio>` e os secrets de SSH não pertencem ao repositório e devem ser provisionados pelo responsável pela infraestrutura. O compose exige os dois domínios para impedir um deploy acidental com placeholders locais.

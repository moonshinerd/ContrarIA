## Descrição
<!-- O que muda e por quê. Se for uma decisão (modelo, fonte, threshold), registre o motivo aqui. -->

## Issue relacionada
Closes #

## Área afetada
- [ ] `api/` (serviço/worker)
- [ ] `research/` (datasets, benchmark)
- [ ] `docs/` (MkDocs, atas, ADRs)
- [ ] Infra (Docker, CI, deploy)

## Como testar
<!-- Passos para validar -->

## Checklist
- [ ] Branch `feature/*` a partir de `main`
- [ ] Revisado pela outra pessoa da dupla
- [ ] Não expõe segredos (App Password, chaves de API) nem em fixtures
- [ ] Se mexeu em `api/`: `make lint` e `make test` passam
- [ ] Se mudou `app/domain/entities.py` (contrato): avisou as outras duplas
- [ ] Se mudou comportamento: docs/README atualizados

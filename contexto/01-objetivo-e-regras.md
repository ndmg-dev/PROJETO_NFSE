# 01 — Objetivo, stack e regras de trabalho

## Objetivo
Plataforma que captura NFS-e do padrão nacional (ADN / gov.br) de vários CNPJs, cada um com o
certificado A1 da empresa, e gera relatórios fiscais para um escritório contábil. Substitui a
exportação manual do Portal Nacional (uma empresa e um mês por vez).

## Princípio de produto (do dono do projeto)
> "Eu quero criar algo pra facilitar a vida do contador, não pra dificultar. Se ele tiver que
> fazer inúmeros processos repetitivos, a aplicação não serviu de nada."

Também: **"Não quero ter que digitar comandos nem nada do tipo"**: tudo por link, interface ou duplo clique.

## Stack
Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy 2 + Alembic, Pydantic v2, httpx, pytest + respx,
openpyxl, ruff, mypy strict no domínio. Docker Compose (modo servidor) ou instalação local no
Windows sem Docker. Celery + Redis existem só para os workers e são **opcionais** no modo local.

## As regras de trabalho (do prompt inicial)
1. Trabalhar em **fases**, com plano curto antes de cada uma.
2. **Nunca inventar campos ou rotas do ADN.** Parar e perguntar, ou descobrir com o certificado.
3. Todo dinheiro é `Decimal`/`numeric`. Nenhum `float`.
4. Segredos (`.pfx`, senhas, DSN) nunca no repositório, em log, em erro ou na API.
5. Testes junto do código, **incluindo casos degenerados**.
6. Não ajustar o resultado para "bater": se o critério de aceite falhar, investigar.
7. Commits pequenos, em português, um assunto cada, terminando com
   `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
8. Dizer explicitamente quando a spec não couber.

## Critério de aceite da Fase 0
AB Engenharia (CNPJ 07.199.546/0001-62), 08/2026, como tomadora: **78 notas, R$ 198.227,91**.
Se não bater: investigar (hipótese: cobertura municipal) e **não ajustar para bater**.
**Status: BLOQUEADA** (falta o `.pfx` da AB e o contrato do ADN).

# 08 — Comandos e testes

Tudo roda em container: a máquina de desenvolvimento não precisa de Python com pip.

| Comando | O que faz |
|---|---|
| `make up` / `make down` | Sobe/derruba banco e redis (Docker) |
| `make migrate` | Aplica as migrations |
| `make test` | Testes Python contra PostgreSQL real (443) |
| `make lint` / `make types` | ruff; mypy strict no domínio |
| `make test-web` | Páginas HTML em jsdom |
| `make test-windows` | Instaladores em PowerShell 7 (gera os `.bat` antes) |
| `make test-local` | Ensaio da instalação local no Linux (com os binários do PG 16.15) |
| `make test-agente` | Lógica Java do cadastro, servidor de mentira |
| `make instalador-windows` | Gera `dist/Instalar-NFSe.bat` |
| `make reversivel` | `downgrade base` + `upgrade head` |

## Gate antes de commitar
Rode lint e testes **gravando em arquivo e conferindo o código de saída** (não use pipe com `tail`).

## Convenções
Commits em português, um assunto por commit, com a linha `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
Arquivos `.ps1` do instalador: sem BOM nos que são concatenados (`comum_nfse.ps1`, `instalar_nfse.ps1`, `lib_windows.ps1`).
O `iniciar.ps1` é UTF-8 com BOM e CRLF (`.gitattributes`).

## Publicar
Push com header temporário (não embutir token na URL); Release por API do GitHub, substituindo os assets.
Nunca gravar token em arquivo, log ou commit.

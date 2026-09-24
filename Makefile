# Atalhos. Tudo roda em container: a máquina não precisa de Python com pip.
PW  = $(shell grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
APW = $(shell grep '^APP_DB_PASSWORD='  .env | cut -d= -f2-)
ADMIN = -e DATABASE_URL="postgresql+psycopg://nfse:$(PW)@db:5432/nfse" -e APP_DB_PASSWORD="$(APW)"
JS  = $(shell grep '^JWT_SECRET=' .env | cut -d= -f2-)
APP   = -e DATABASE_URL="postgresql+psycopg://nfse_app:$(APW)@db:5432/nfse" \
        -e ADMIN_DATABASE_URL="postgresql+psycopg://nfse:$(PW)@db:5432/nfse" \
        -e JWT_SECRET="$(JS)" \
        -e REDIS_URL="redis://redis:6379/0"
RUN   = docker compose run --rm

.PHONY: up down build migrate test test-web test-windows lint types reversivel
up:      ; docker compose up -d db redis
down:    ; docker compose down
build:   ; docker compose build
migrate: ; $(RUN) $(ADMIN) api alembic upgrade head
test:    ; $(RUN) $(APP) api pytest tests poc/tests -q
# Páginas HTML em jsdom (assistente de primeiro acesso). Separado do `make test`:
# precisa de Node, que roda em container, e de rede para baixar o jsdom.
test-web: ; docker run --rm --user "$$(id -u):$$(id -g)" -e HOME=/tmp -v "$(CURDIR)":/work -w /work/tests/web node:22-slim sh -c "npm i --no-package-lock --no-audit --no-fund --loglevel=error && node wizard_check.js /work/app/web/setup.html"
# Instalador do Windows em PowerShell 7 (container). Prova sintaxe e lógica pura;
# NÃO prova o Windows PowerShell 5.1 nem docker/navegador/icacls do Windows.
test-windows: ; docker run --rm -v "$(CURDIR)":/work:ro -w /work mcr.microsoft.com/powershell:latest pwsh -NoProfile -File tests/windows/iniciar.tests.ps1
lint:    ; $(RUN) --no-deps api ruff check app poc tests
types:   ; $(RUN) --no-deps api mypy app/domain/ app/adn/ app/core/dinheiro.py
reversivel: ; $(RUN) $(ADMIN) api sh -c "alembic downgrade base && alembic upgrade head"

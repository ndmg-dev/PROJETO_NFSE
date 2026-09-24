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

.PHONY: up down build migrate test test-web test-windows test-local instalador-windows lint types reversivel
up:      ; docker compose up -d db redis
down:    ; docker compose down
build:   ; docker compose build
migrate: ; $(RUN) $(ADMIN) api alembic upgrade head
test:    ; $(RUN) $(APP) api pytest tests poc/tests -q
# Páginas HTML em jsdom (assistente de primeiro acesso). Separado do `make test`:
# precisa de Node, que roda em container, e de rede para baixar o jsdom.
test-web: ; docker run --rm --user "$$(id -u):$$(id -g)" -e HOME=/tmp -v "$(CURDIR)":/work -w /work/tests/web node:22-slim sh -c "npm i --no-package-lock --no-audit --no-fund --loglevel=error && node wizard_check.js /work/app/web/setup.html && node instalar_check.js /work/app/web/instalar.html"
# Instaladores do Windows em PowerShell 7 (container). Provam sintaxe, o arquivo
# gerado pelo servidor e a lógica pura; NAO provam o Windows PowerShell 5.1 nem
# docker, navegador, javac, atalho (COM) e SunMSCAPI do Windows.
test-windows:
	mkdir -p .tmp-windows
	$(RUN) --no-deps --user "$$(id -u):$$(id -g)" api python -m app.instalador.agente --url http://servidor-de-teste:8000 --saida /app/.tmp-windows/Instalar-Agente-NFSe.bat
	docker run --rm -v "$(CURDIR)":/work:ro -w /work mcr.microsoft.com/powershell:latest pwsh -NoProfile -File tests/windows/todos.ps1
# Ensaio da instalação local (sem Docker) no Linux, com os mesmos binários de
# PostgreSQL 16.15.0. Prova a sequência e o modo local da aplicação; NAO prova nada
# especifico do Windows. Roda como usuario comum (o PostgreSQL recusa root).
test-local: ; docker run --rm -v "$(CURDIR)":/repo:ro python:3.12-slim sh -c "useradd -m ensaio && su ensaio -c 'REPO=/repo python /repo/tests/local/ensaio_linux.py'"
# Gera Instalar-NFSe.bat (instalação local, sem Docker) em dist/.
instalador-windows:
	mkdir -p dist
	$(RUN) --no-deps --user "$$(id -u):$$(id -g)" api python -m app.instalador.local --saida /app/dist/Instalar-NFSe.bat
lint:    ; $(RUN) --no-deps api ruff check app poc tests
types:   ; $(RUN) --no-deps api mypy app/domain/ app/adn/ app/core/dinheiro.py
reversivel: ; $(RUN) $(ADMIN) api sh -c "alembic downgrade base && alembic upgrade head"

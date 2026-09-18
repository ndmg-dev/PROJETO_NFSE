# Atalhos. Tudo roda em container: a máquina não precisa de Python com pip.
PW  = $(shell grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
APW = $(shell grep '^APP_DB_PASSWORD='  .env | cut -d= -f2-)
ADMIN = -e DATABASE_URL="postgresql+psycopg://nfse:$(PW)@db:5432/nfse" -e APP_DB_PASSWORD="$(APW)"
APP   = -e DATABASE_URL="postgresql+psycopg://nfse_app:$(APW)@db:5432/nfse" \
        -e ADMIN_DATABASE_URL="postgresql+psycopg://nfse:$(PW)@db:5432/nfse"
RUN   = docker compose run --rm

.PHONY: up down build migrate test lint types reversivel
up:      ; docker compose up -d db redis
down:    ; docker compose down
build:   ; docker compose build
migrate: ; $(RUN) $(ADMIN) api alembic upgrade head
test:    ; $(RUN) $(APP) api pytest tests poc/tests -q
lint:    ; $(RUN) --no-deps api ruff check app poc tests
types:   ; $(RUN) --no-deps api mypy app/domain app/core/dinheiro.py
reversivel: ; $(RUN) $(ADMIN) api sh -c "alembic downgrade base && alembic upgrade head"

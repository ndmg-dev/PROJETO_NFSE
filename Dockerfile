FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq5 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; \
    else pip install -r requirements.txt; fi

COPY . .

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --- Instalação (docker-compose.instalacao.yml): sem privilégio de root -----
FROM base AS instalacao
RUN useradd --system --uid 10001 --create-home app \
 && mkdir -p /data/xml \
 && chown -R app:app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"


# --- Desenvolvimento -------------------------------------------------------
# Último estágio = o que `docker compose build` constrói quando não há
# `target`. Roda como root e monta o código do disco (docker-compose.yml).
FROM base AS dev

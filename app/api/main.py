from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app.api.routers import auth, empresas, relatorios, setup
from app.core.config import obter_config
from app.setup.codigo import codigo_de_configuracao
from app.setup.verificacoes import setup_concluido

# uvicorn.error é o logger que o uvicorn deixa visível em INFO; o logger da app
# ficaria calado e o dono do servidor nunca veria o código.
_log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    if setup_concluido() is not True:
        codigo = codigo_de_configuracao(obter_config().jwt_secret.get_secret_value())
        _log.info("PRIMEIRO ACESSO: abra /setup no navegador. "
                  "Código de configuração: %s", codigo)
    yield


app = FastAPI(title="NFS-e Nacional", version="0.1.0", lifespan=_ciclo_de_vida)
app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(empresas.router)
app.include_router(relatorios.router)

_WEB = Path(__file__).resolve().parent.parent / "web"


@app.get("/", include_in_schema=False)
def painel() -> Response:
    """Painel web (login + empresas). Se o sistema ainda não foi configurado,
    manda para o assistente de primeiro acesso em vez de um login sem conta."""
    if setup_concluido() is False:
        return RedirectResponse("/setup")
    return FileResponse(_WEB / "index.html")


@app.get("/setup", include_in_schema=False)
def assistente() -> FileResponse:
    return FileResponse(_WEB / "setup.html")


@app.exception_handler(Exception)
async def erro_inesperado(request: Request, exc: Exception) -> JSONResponse:
    """Nunca devolver traceback: ele pode conter caminho de .pfx ou DSN."""
    return JSONResponse(
        status_code=500,
        content={"type": "about:blank", "title": "erro interno", "status": 500},
        media_type="application/problem+json",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

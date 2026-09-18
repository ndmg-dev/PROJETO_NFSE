from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import auth, empresas

app = FastAPI(title="NFS-e Nacional", version="0.1.0")
app.include_router(auth.router)
app.include_router(empresas.router)


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

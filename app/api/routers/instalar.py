"""Download do instalador do agente (Windows).

Público de propósito: quem abre o link numa estação ainda não tem conta nem
sessão. O arquivo não carrega segredo nenhum (só os fontes públicos do spike e o
endereço deste servidor), e é gerado a cada pedido.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.instalador.agente import gerar_instalador, url_servidor_segura

router = APIRouter(prefix="/instalar", tags=["instalar"])

NOME_DO_ARQUIVO = "Instalar-Agente-NFSe.bat"


@router.get(f"/{NOME_DO_ARQUIVO}")
def baixar_instalador(request: Request) -> Response:
    # O endereço vem do cabeçalho Host, que quem chama controla; só passa se for
    # http(s)://host[:porta] e só vai para servidor.txt.
    corpo = gerar_instalador(url_servidor_segura(str(request.base_url)))
    return Response(
        corpo,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{NOME_DO_ARQUIVO}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.api.schemas import LoginIn, TokenOut
from app.core.config import obter_config
from app.core.seguranca import Identidade, conferir_senha, emitir_token
from app.db.base import criar_sessao

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(dados: LoginIn) -> TokenOut:
    cfg = obter_config()
    # O login precede o tenant: não há escritorio_id para fixar na RLS ainda.
    # autenticar() é SECURITY DEFINER e devolve no máximo uma linha, pelo
    # e-mail exato — ver migration 0004.
    with criar_sessao() as s:
        usuario = s.execute(
            text("SELECT id, escritorio_id, papel, senha_hash, ativo "
                 "FROM autenticar(:email)"),
            {"email": dados.email},
        ).one_or_none()

    # Mesmo erro para usuário inexistente e senha errada: diferenciar entrega
    # enumeração de contas.
    if usuario is None or not usuario.ativo or not conferir_senha(
        dados.senha, usuario.senha_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciais inválidas"
        )

    identidade = Identidade(
        usuario_id=usuario.id,
        escritorio_id=usuario.escritorio_id,
        papel=usuario.papel,  # type: ignore[arg-type]
    )
    segredo = cfg.jwt_secret.get_secret_value()
    return TokenOut(
        access_token=emitir_token(
            identidade, segredo, minutos=cfg.access_token_minutos
        ),
        refresh_token=emitir_token(
            identidade, segredo, minutos=cfg.refresh_token_dias * 24 * 60,
            tipo="refresh",
        ),
    )

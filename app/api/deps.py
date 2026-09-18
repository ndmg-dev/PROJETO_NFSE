"""Dependências da API: identidade do JWT e sessão com RLS aplicada."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import obter_config
from app.core.seguranca import AuthError, Identidade, Papel, ler_token
from app.db.base import criar_sessao


def identidade_atual(authorization: str = Header(default="")) -> Identidade:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="credenciais ausentes",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return ler_token(
            authorization.removeprefix("Bearer ").strip(),
            obter_config().jwt_secret.get_secret_value(),
        )
    except AuthError:
        # Detalhe genérico de propósito: distinguir "expirado" de "assinatura
        # inválida" para o cliente entrega informação a quem está sondando.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def sessao(identidade: Identidade = Depends(identidade_atual)) -> Iterator[Session]:
    """Sessão com o escopo de tenant fixado no banco, não na aplicação."""
    with criar_sessao() as s:
        s.execute(
            text("SELECT set_config('app.escritorio_id', :eid, true)"),
            {"eid": str(identidade.escritorio_id)},
        )
        yield s
        s.commit()


def exigir_papel(*papeis: Papel):  # type: ignore[no-untyped-def]
    def verificar(identidade: Identidade = Depends(identidade_atual)) -> Identidade:
        if identidade.papel not in papeis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="papel insuficiente"
            )
        return identidade

    return verificar

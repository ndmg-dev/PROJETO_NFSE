"""Primeiro acesso: verificações do sistema e criação do escritório + admin.

Público de propósito (ainda não há login) e por isso o mais cuidadoso da API:
  - só funciona enquanto NÃO existe nenhum usuário; depois disso, tranca de vez;
  - exige o código de configuração (app/setup/codigo.py);
  - limita tentativas erradas;
  - a criação é atômica no banco, então dois setups simultâneos não geram dois
    administradores (migration 0007).
"""

from __future__ import annotations

import ipaddress
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import obter_config
from app.core.seguranca import hash_senha
from app.db.base import criar_sessao
from app.setup.codigo import codigo_confere
from app.setup.limite import LimitadorDeTentativas
from app.setup.verificacoes import Verificacao, setup_concluido, verificar_sistema

log = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])

# 5 erros por origem a cada 5 minutos, e 30 no total para quem distribui.
LIMITE_POR_ORIGEM = LimitadorDeTentativas(maximo=5, janela_s=300)
LIMITE_GLOBAL = LimitadorDeTentativas(maximo=30, janela_s=300)
_CHAVE_GLOBAL = "*"


class VerificacaoOut(BaseModel):
    id: str
    rotulo: str
    ok: bool
    detalhe: str | None = None


class StatusOut(BaseModel):
    # None = não foi possível saber (banco fora do ar ou estrutura não criada)
    configurado: bool | None
    verificacoes: list[VerificacaoOut]


class SetupIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    escritorio: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=10, max_length=200)


class SetupOut(BaseModel):
    ok: bool = True


def _saida(v: Verificacao) -> VerificacaoOut:
    return VerificacaoOut(id=v.id, rotulo=v.rotulo, ok=v.ok, detalhe=v.detalhe)


def _origem(request: Request) -> str:
    return request.client.host if request.client else "desconhecida"


def _ip_valido(origem: str) -> str | None:
    try:
        return str(ipaddress.ip_address(origem))
    except ValueError:
        return None


@router.get("/status", response_model=StatusOut)
def estado() -> StatusOut:
    configurado = setup_concluido()
    if configurado:
        # Depois do setup, nada de detalhe de infraestrutura para anônimo.
        return StatusOut(configurado=True, verificacoes=[])
    return StatusOut(
        configurado=configurado,
        verificacoes=[_saida(v) for v in verificar_sistema()],
    )


@router.post("", response_model=SetupOut, status_code=status.HTTP_201_CREATED)
def configurar(dados: SetupIn, request: Request) -> SetupOut:
    if setup_concluido():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="O sistema já foi configurado."
        )

    origem = _origem(request)
    if LIMITE_POR_ORIGEM.bloqueado(origem) or LIMITE_GLOBAL.bloqueado(_CHAVE_GLOBAL):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas com código incorreto. Aguarde alguns minutos.",
        )

    segredo = obter_config().jwt_secret.get_secret_value()
    if not codigo_confere(dados.codigo, segredo):
        LIMITE_POR_ORIGEM.registrar_falha(origem)
        LIMITE_GLOBAL.registrar_falha(_CHAVE_GLOBAL)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Código de configuração incorreto.",
        )

    email = dados.email.strip().lower()
    try:
        with criar_sessao() as s:
            criado = s.execute(
                text("SELECT escritorio_id, usuario_id "
                     "FROM criar_primeiro_acesso(:escritorio, :email, :hash)"),
                {"escritorio": dados.escritorio.strip(), "email": email,
                 "hash": hash_senha(dados.senha)},
            ).one()
            s.execute(
                text("INSERT INTO audit_log (escritorio_id, usuario_id, acao, recurso, ip) "
                     "VALUES (:e, :u, 'setup.primeiro_acesso', 'sistema', CAST(:ip AS inet))"),
                {"e": criado.escritorio_id, "u": criado.usuario_id, "ip": _ip_valido(origem)},
            )
            s.commit()
    except DBAPIError as exc:
        if "setup_ja_concluido" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="O sistema já foi configurado."
            ) from None
        log.exception("falha ao criar o primeiro acesso")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível concluir a configuração. Verifique o banco de dados.",
        ) from None

    log.info("primeiro acesso configurado a partir de %s", origem)
    return SetupOut()

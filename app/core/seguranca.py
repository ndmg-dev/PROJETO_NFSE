"""Senhas e tokens (spec §6, §8)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt

# bcrypt direto em vez de passlib: passlib 1.7.4 importa o módulo `crypt`, que
# foi removido no Python 3.13, e está sem manutenção. Trocar depois seria pior.
CUSTO_BCRYPT = 12
LIMITE_BCRYPT = 72  # bytes; o algoritmo trunca além disso, em silêncio

Papel = Literal["admin", "operador", "leitura"]
PAPEIS: tuple[Papel, ...] = ("admin", "operador", "leitura")


class AuthError(Exception):
    """Falha de autenticação. Mensagem sempre genérica para o cliente."""


def _preparar(senha: str) -> bytes:
    """bcrypt trunca em 72 bytes sem avisar: duas senhas longas com o mesmo
    prefixo passariam uma pela outra. O SHA-256 antes normaliza o tamanho."""
    return base64.b64encode(hashlib.sha256(senha.encode()).digest())


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(_preparar(senha), bcrypt.gensalt(CUSTO_BCRYPT)).decode()


def conferir_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        return bcrypt.checkpw(_preparar(senha), hash_armazenado.encode())
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Identidade:
    usuario_id: uuid.UUID
    escritorio_id: uuid.UUID
    papel: Papel


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def emitir_token(
    identidade: Identidade, segredo: str, *, minutos: int, tipo: str = "access"
) -> str:
    agora = datetime.now(UTC)
    corpo = {
        "sub": str(identidade.usuario_id),
        "esc": str(identidade.escritorio_id),
        "pap": identidade.papel,
        "typ": tipo,
        "iat": int(agora.timestamp()),
        "exp": int((agora + timedelta(minutes=minutos)).timestamp()),
        "jti": os.urandom(8).hex(),
    }
    cabecalho = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    carga = _b64(json.dumps(corpo, separators=(",", ":")).encode())
    assinatura = _b64(_assinar(f"{cabecalho}.{carga}", segredo))
    return f"{cabecalho}.{carga}.{assinatura}"


def _assinar(dados: str, segredo: str) -> bytes:
    return hmac.new(segredo.encode(), dados.encode(), hashlib.sha256).digest()


def ler_token(token: str, segredo: str, *, tipo: str = "access") -> Identidade:
    partes = token.split(".")
    if len(partes) != 3:
        raise AuthError("token malformado")
    cabecalho, carga, assinatura = partes

    esperada = _b64(_assinar(f"{cabecalho}.{carga}", segredo))
    # compare_digest: comparação em tempo constante evita oráculo por timing.
    if not hmac.compare_digest(assinatura, esperada):
        raise AuthError("assinatura inválida")

    try:
        corpo: dict[str, Any] = json.loads(_desb64(carga))
    except (ValueError, json.JSONDecodeError):
        raise AuthError("token malformado") from None

    # "alg": "none" e troca de algoritmo não são aceitos: só validamos HS256
    # acima, e o cabeçalho recebido nunca escolhe o algoritmo.
    if corpo.get("typ") != tipo:
        raise AuthError("tipo de token incorreto")
    if int(corpo.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        raise AuthError("token expirado")
    papel = corpo.get("pap")
    if papel not in PAPEIS:
        raise AuthError("papel desconhecido")

    try:
        return Identidade(
            usuario_id=uuid.UUID(corpo["sub"]),
            escritorio_id=uuid.UUID(corpo["esc"]),
            papel=papel,
        )
    except (KeyError, ValueError):
        raise AuthError("token malformado") from None

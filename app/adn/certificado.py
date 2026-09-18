"""Carga do certificado A1 e montagem do contexto mTLS (spec §3.3, §8).

Invariantes deste módulo:
  - a senha nunca entra em mensagem de exceção, log ou repr;
  - a chave privada em PEM só existe em tmpfs, com modo 600;
  - o PEM é apagado por `ContextoMTLS` ao sair do `with`, inclusive em erro.
"""

from __future__ import annotations

import os
import re
import ssl
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Final

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509 import Certificate
from cryptography.x509.oid import NameOID

DIRETORIOS_TMPFS: Final = ("/dev/shm",)


class CertificadoError(Exception):
    """Falha de certificado. Nunca carrega senha nem material de chave."""


@dataclass(frozen=True)
class MetadadosCertificado:
    """O único recorte do certificado que pode sair por API (spec §8)."""

    titular_cnpj: str
    titular_nome: str
    valido_de: date
    valido_ate: date

    @property
    def cnpj_raiz(self) -> str:
        return self.titular_cnpj[:8]

    def vencido_em(self, referencia: date) -> bool:
        return referencia > self.valido_ate

    def dias_para_vencer(self, referencia: date) -> int:
        return (self.valido_ate - referencia).days


def _tmpfs() -> Path:
    for candidato in DIRETORIOS_TMPFS:
        p = Path(candidato)
        if p.is_dir() and os.access(p, os.W_OK):
            return p
    raise CertificadoError(
        "Nenhum tmpfs gravável. Recuso escrever chave privada em disco "
        "persistente (spec §8)."
    )


def ler_metadados(pfx_bytes: bytes, senha: bytes) -> MetadadosCertificado:
    _, cert, _ = _abrir(pfx_bytes, senha)
    return _metadados(cert)


def _abrir(pfx_bytes: bytes, senha: bytes):  # type: ignore[no-untyped-def]
    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(pfx_bytes, senha)
    except Exception as exc:
        # Só o tipo da exceção: a mensagem da cryptography pode citar a senha.
        raise CertificadoError(
            f"Não foi possível abrir o .pfx ({type(exc).__name__}). "
            "Senha incorreta ou arquivo inválido."
        ) from None
    if chave is None or cert is None:
        raise CertificadoError("O .pfx não contém par chave/certificado utilizável.")
    return chave, cert, cadeia


def _metadados(cert: Certificate) -> MetadadosCertificado:
    atributos = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = str(atributos[0].value) if atributos else ""
    # e-CNPJ da ICP-Brasil usa CN "RAZAO SOCIAL:CNPJ".
    encontrados = re.findall(r"\d{14}", cn)
    return MetadadosCertificado(
        titular_cnpj=encontrados[0] if encontrados else "",
        titular_nome=cn.split(":")[0].strip(),
        valido_de=cert.not_valid_before_utc.date(),
        valido_ate=cert.not_valid_after_utc.date(),
    )


class ContextoMTLS:
    """Contexto TLS com o A1 apresentado como certificado de cliente.

        with ContextoMTLS(pfx, senha) as ctx:
            httpx.Client(verify=ctx.ssl_context, ...)

    Fora do `with`, o PEM não existe mais.
    """

    def __init__(self, pfx_bytes: bytes, senha: bytes) -> None:
        self._pfx = pfx_bytes
        self._senha = senha
        self._pem: Path | None = None
        self.ssl_context: ssl.SSLContext | None = None
        self.metadados: MetadadosCertificado | None = None

    def __enter__(self) -> ContextoMTLS:
        chave, cert, cadeia = _abrir(self._pfx, self._senha)
        descritor, nome = tempfile.mkstemp(suffix=".pem", dir=_tmpfs())
        self._pem = Path(nome)
        try:
            os.fchmod(descritor, 0o600)
            with os.fdopen(descritor, "wb") as arquivo:
                arquivo.write(cert.public_bytes(Encoding.PEM))
                for intermediario in cadeia or []:
                    arquivo.write(intermediario.public_bytes(Encoding.PEM))
                arquivo.write(
                    chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
                )
            contexto = ssl.create_default_context()
            contexto.minimum_version = ssl.TLSVersion.TLSv1_2
            contexto.load_cert_chain(str(self._pem))
        except BaseException:
            self._apagar()
            raise
        self.ssl_context = contexto
        self.metadados = _metadados(cert)
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._apagar()

    def _apagar(self) -> None:
        if self._pem is not None:
            self._pem.unlink(missing_ok=True)
            self._pem = None

    @property
    def caminho_pem(self) -> Path | None:
        """Exposto só para teste verificar que o arquivo sumiu."""
        return self._pem

    def __repr__(self) -> str:
        return f"<ContextoMTLS titular={self.metadados.titular_cnpj if self.metadados else '?'}>"

"""Cofre de certificados: cifra envelope para .pfx e senhas (spec §8).

Estrutura de envelope, igual à de um KMS: cada segredo é cifrado com uma DEK
(chave de dados) nova, e a DEK é embrulhada por uma KEK (chave mestra). Trocar
o backend local por AWS KMS, GCP KMS ou Vault é trocar `_EnvolucroLocal` por
outra classe — o resto do sistema não muda.

AVISO DE CONFORMIDADE
A §8 exige KEK gerenciada por KMS, explicitamente "não com chave no .env". O
backend local guarda a KEK numa variável de ambiente e está ABAIXO dessa barra.
É aceitável para desenvolvimento. Colocar certificado de cliente real atrás
dele em produção não é: quem lê o .env lê todos os certificados do escritório.
Ver `EnvolucroKMS` para o ponto de troca.
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TAMANHO_DEK: Final = 32
TAMANHO_NONCE: Final = 12
VERSAO: Final = b"\x01"


class CofreError(Exception):
    """Falha do cofre. A mensagem nunca contém material de chave."""


@dataclass(frozen=True)
class Envelope:
    """Segredo cifrado, pronto para ir para o banco como `bytea`."""

    bytes_: bytes

    def __repr__(self) -> str:  # nunca despejar conteúdo em traceback
        return f"<Envelope {len(self.bytes_)} bytes>"


class Envolucro(ABC):
    """Quem embrulha e desembrulha a DEK. É aqui que o KMS entra."""

    @abstractmethod
    def embrulhar(self, dek: bytes) -> bytes: ...

    @abstractmethod
    def desembrulhar(self, dek_embrulhada: bytes) -> bytes: ...


class EnvolucroLocal(Envolucro):
    """KEK em memória, vinda do ambiente. Só para desenvolvimento."""

    def __init__(self, kek: bytes) -> None:
        if len(kek) != 32:
            raise CofreError("KEK precisa ter 32 bytes.")
        self._aes = AESGCM(kek)

    def embrulhar(self, dek: bytes) -> bytes:
        nonce = os.urandom(TAMANHO_NONCE)
        return nonce + self._aes.encrypt(nonce, dek, b"dek")

    def desembrulhar(self, dek_embrulhada: bytes) -> bytes:
        nonce, corpo = dek_embrulhada[:TAMANHO_NONCE], dek_embrulhada[TAMANHO_NONCE:]
        try:
            return self._aes.decrypt(nonce, corpo, b"dek")
        except InvalidTag:
            raise CofreError("DEK não autentica — KEK errada ou dado adulterado.") from None


class EnvolucroKMS(Envolucro):
    """Ponto de troca para produção (spec §8).

    Implementar com `kms:Encrypt`/`kms:Decrypt` (AWS), `CryptoKey.encrypt`
    (GCP) ou o transit engine do Vault. A DEK nunca sai do processo em claro
    para o serviço: o KMS só vê a DEK embrulhada.
    """

    def __init__(self, key_id: str) -> None:
        self.key_id = key_id

    def embrulhar(self, dek: bytes) -> bytes:
        raise NotImplementedError(
            "Backend de KMS não implementado. Antes de produção com certificado "
            "real, implemente aqui — o EnvolucroLocal não atende a §8."
        )

    def desembrulhar(self, dek_embrulhada: bytes) -> bytes:
        raise NotImplementedError("Backend de KMS não implementado.")


class Cofre:
    """Cifra e decifra segredos. Nada aqui registra o conteúdo em log."""

    def __init__(self, envolucro: Envolucro) -> None:
        self._envolucro = envolucro

    def guardar(self, segredo: bytes, contexto: str) -> Envelope:
        """`contexto` vira dado autenticado: um envelope de empresa A não
        decifra como se fosse da empresa B, mesmo com a KEK certa."""
        if not segredo:
            raise CofreError("Recusando guardar segredo vazio.")
        dek = os.urandom(TAMANHO_DEK)
        nonce = os.urandom(TAMANHO_NONCE)
        corpo = AESGCM(dek).encrypt(nonce, segredo, contexto.encode())
        embrulhada = self._envolucro.embrulhar(dek)
        return Envelope(
            VERSAO
            + len(embrulhada).to_bytes(2, "big")
            + embrulhada
            + nonce
            + corpo
        )

    def abrir(self, envelope: Envelope | bytes, contexto: str) -> bytes:
        bruto = envelope.bytes_ if isinstance(envelope, Envelope) else envelope
        if not bruto or bruto[:1] != VERSAO:
            raise CofreError("Envelope com versão desconhecida ou vazio.")
        tamanho = int.from_bytes(bruto[1:3], "big")
        embrulhada = bruto[3 : 3 + tamanho]
        resto = bruto[3 + tamanho :]
        nonce, corpo = resto[:TAMANHO_NONCE], resto[TAMANHO_NONCE:]
        dek = self._envolucro.desembrulhar(embrulhada)
        try:
            return AESGCM(dek).decrypt(nonce, corpo, contexto.encode())
        except InvalidTag:
            raise CofreError(
                "Segredo não autentica — contexto errado ou dado adulterado."
            ) from None


def cofre_padrao() -> Cofre:
    from app.core.config import obter_config

    kek = base64.b64decode(obter_config().cofre_master_key.get_secret_value())
    return Cofre(EnvolucroLocal(kek))

"""O cofre é o capítulo que decide se o sistema pode existir (spec §8)."""

from __future__ import annotations

import os

import pytest

from app.core.cofre import (
    Cofre,
    CofreError,
    EnvolucroKMS,
    EnvolucroLocal,
)

SENHA = b"senha-do-pfx-do-cliente"
PFX = b"\x30\x82" + os.urandom(2048)  # finge um .pfx pelo tamanho, não pelo conteúdo


@pytest.fixture
def cofre() -> Cofre:
    return Cofre(EnvolucroLocal(os.urandom(32)))


def test_ida_e_volta(cofre: Cofre) -> None:
    env = cofre.guardar(PFX, contexto="empresa:07199546000162")
    assert cofre.abrir(env, contexto="empresa:07199546000162") == PFX


def test_texto_cifrado_nao_contem_o_segredo(cofre: Cofre) -> None:
    env = cofre.guardar(SENHA, contexto="empresa:x")
    assert SENHA not in env.bytes_


def test_mesmo_segredo_gera_envelopes_diferentes(cofre: Cofre) -> None:
    """Sem isso, dá para saber que dois clientes usam a mesma senha."""
    a = cofre.guardar(SENHA, contexto="empresa:x")
    b = cofre.guardar(SENHA, contexto="empresa:x")
    assert a.bytes_ != b.bytes_


def test_contexto_errado_nao_abre(cofre: Cofre) -> None:
    """O certificado da empresa A não decifra como se fosse da empresa B."""
    env = cofre.guardar(PFX, contexto="empresa:aaa")
    with pytest.raises(CofreError, match="contexto errado"):
        cofre.abrir(env, contexto="empresa:bbb")


def test_kek_errada_nao_abre(cofre: Cofre) -> None:
    env = cofre.guardar(PFX, contexto="empresa:x")
    outro = Cofre(EnvolucroLocal(os.urandom(32)))
    with pytest.raises(CofreError):
        outro.abrir(env, contexto="empresa:x")


@pytest.mark.parametrize("posicao", [3, 20, -1])
def test_adulteracao_e_detectada(cofre: Cofre, posicao: int) -> None:
    """AES-GCM é autenticado: byte trocado no banco não passa despercebido."""
    env = cofre.guardar(PFX, contexto="empresa:x")
    corrompido = bytearray(env.bytes_)
    corrompido[posicao] ^= 0x01
    with pytest.raises(CofreError):
        cofre.abrir(bytes(corrompido), contexto="empresa:x")


def test_envelope_nao_vaza_em_repr(cofre: Cofre) -> None:
    """Traceback e log de debug imprimem repr. Não pode sair segredo."""
    env = cofre.guardar(SENHA, contexto="empresa:x")
    texto = f"{env!r} {env}"
    assert SENHA.decode() not in texto
    assert "Envelope" in texto


def test_recusa_segredo_vazio(cofre: Cofre) -> None:
    with pytest.raises(CofreError):
        cofre.guardar(b"", contexto="empresa:x")


def test_recusa_kek_de_tamanho_errado() -> None:
    with pytest.raises(CofreError, match="32 bytes"):
        EnvolucroLocal(os.urandom(16))


def test_envelope_vazio_ou_com_versao_desconhecida(cofre: Cofre) -> None:
    for ruim in (b"", b"\x99abc"):
        with pytest.raises(CofreError, match="versão desconhecida|vazio"):
            cofre.abrir(ruim, contexto="empresa:x")


def test_backend_kms_falha_alto_em_vez_de_fingir() -> None:
    """Se alguém apontar para KMS sem implementar, tem que quebrar na cara."""
    kms = EnvolucroKMS(key_id="arn:aws:kms:...")
    with pytest.raises(NotImplementedError, match="§8"):
        kms.embrulhar(os.urandom(32))

"""Carga do A1 (spec §3.3, §8).

O .pfx destes testes é autoassinado e gerado na hora — serve para exercitar
parsing, cifra e limpeza de arquivo. Ele NÃO é usado para fingir que o ADN
respondeu: contrato de API fiscal só se descobre com certificado real.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.adn.certificado import (
    CertificadoError,
    ContextoMTLS,
    ler_metadados,
)

SENHA = b"senha-secreta-do-teste"
CNPJ = "07199546000162"


def gerar_pfx(
    cn: str = f"AB ENGENHARIA LTDA:{CNPJ}",
    dias_validade: int = 365,
    senha: bytes = SENHA,
) -> bytes:
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    agora = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(days=abs(dias_validade) + 1))
        .not_valid_after(agora + dt.timedelta(days=dias_validade))
        .sign(chave, hashes.SHA256())
    )
    return serialization.pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha),
    )


@pytest.fixture(scope="module")
def pfx() -> bytes:
    return gerar_pfx()


def test_extrai_cnpj_e_raiz(pfx: bytes) -> None:
    m = ler_metadados(pfx, SENHA)
    assert m.titular_cnpj == CNPJ
    assert m.cnpj_raiz == "07199546"
    assert m.titular_nome == "AB ENGENHARIA LTDA"


def test_extrai_validade(pfx: bytes) -> None:
    m = ler_metadados(pfx, SENHA)
    assert m.valido_ate > m.valido_de
    assert m.dias_para_vencer(m.valido_ate) == 0
    assert not m.vencido_em(m.valido_ate)
    assert m.vencido_em(m.valido_ate + dt.timedelta(days=1))


def test_alerta_de_vencimento(pfx: bytes) -> None:
    """A §8 pede alerta em 30/15/7 dias."""
    m = ler_metadados(pfx, SENHA)
    assert m.dias_para_vencer(m.valido_ate - dt.timedelta(days=30)) == 30


def test_senha_errada_nao_vaza_a_senha(pfx: bytes) -> None:
    with pytest.raises(CertificadoError) as exc:
        ler_metadados(pfx, b"senha-errada")
    texto = str(exc.value)
    assert "senha-errada" not in texto
    assert SENHA.decode() not in texto
    assert "Senha incorreta" in texto


def test_arquivo_corrompido_nao_vaza_a_senha() -> None:
    with pytest.raises(CertificadoError) as exc:
        ler_metadados(b"isto nao e um pfx", SENHA)
    assert SENHA.decode() not in str(exc.value)


def test_cn_sem_cnpj_nao_inventa_numero() -> None:
    m = ler_metadados(gerar_pfx(cn="SEM CNPJ NO NOME"), SENHA)
    assert m.titular_cnpj == ""


def test_contexto_mtls_cria_e_apaga_o_pem(pfx: bytes) -> None:
    with ContextoMTLS(pfx, SENHA) as ctx:
        assert ctx.ssl_context is not None
        caminho = ctx.caminho_pem
        assert caminho is not None
        assert caminho.exists()
        assert str(caminho).startswith("/dev/shm"), "PEM fora de tmpfs"
        assert caminho.stat().st_mode & 0o777 == 0o600
    assert not caminho.exists(), "PEM sobreviveu ao with"


def test_pem_apagado_mesmo_com_excecao_dentro_do_with(pfx: bytes) -> None:
    caminho: Path | None = None
    with pytest.raises(RuntimeError), ContextoMTLS(pfx, SENHA) as ctx:
        caminho = ctx.caminho_pem
        raise RuntimeError("falha no meio da sincronização")
    assert caminho is not None and not caminho.exists()


def test_senha_errada_nao_deixa_pem_para_tras(pfx: bytes) -> None:
    antes = set(Path("/dev/shm").glob("*.pem"))
    with pytest.raises(CertificadoError), ContextoMTLS(pfx, b"errada"):
        pass
    assert set(Path("/dev/shm").glob("*.pem")) == antes


def test_repr_nao_vaza_nada(pfx: bytes) -> None:
    with ContextoMTLS(pfx, SENHA) as ctx:
        texto = repr(ctx)
    assert SENHA.decode() not in texto
    assert "BEGIN" not in texto


def test_cofre_e_certificado_juntos(pfx: bytes) -> None:
    """O fluxo real: cifra no banco, decifra em memória, usa, apaga."""
    from app.core.cofre import Cofre, EnvolucroLocal

    cofre = Cofre(EnvolucroLocal(os.urandom(32)))
    contexto = f"empresa:{CNPJ}"
    env_pfx = cofre.guardar(pfx, contexto)
    env_senha = cofre.guardar(SENHA, contexto)

    assert pfx not in env_pfx.bytes_
    assert SENHA not in env_senha.bytes_

    with ContextoMTLS(
        cofre.abrir(env_pfx, contexto), cofre.abrir(env_senha, contexto)
    ) as ctx:
        assert ctx.metadados is not None
        assert ctx.metadados.titular_cnpj == CNPJ

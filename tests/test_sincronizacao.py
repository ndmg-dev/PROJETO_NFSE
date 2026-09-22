"""Invariantes do loop de sincronização (spec §3.4)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.adn.cliente import AdnIndisponivel, AdnRecusou, RespostaDFe
from app.adn.contrato import DocumentoDFe, Lote
from app.core.armazenamento import ArmazenamentoLocal, sha256
from app.workers.sincronizacao import (
    ResultadoSync,
    detectar_lacunas,
    sincronizar_empresa,
)

EMPRESA = uuid.uuid4()


def doc(nsu: int, xml: bytes | None = None, tipo: str = "NFSe") -> DocumentoDFe:
    return DocumentoDFe(nsu=nsu, xml=xml or f"<NFSe n='{nsu}'/>".encode(), tipo=tipo)


class ClienteFalso:
    """Devolve respostas roteirizadas e registra os NSUs pedidos."""

    def __init__(self, roteiro: list[RespostaDFe | Exception]) -> None:
        self.roteiro = roteiro
        self.pedidos: list[int] = []

    def buscar_dfe(self, nsu: int, cnpj_consulta: str | None = None) -> RespostaDFe:
        self.pedidos.append(nsu)
        if not self.roteiro:
            return RespostaDFe(lote=None, status=204)
        proxima = self.roteiro.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima


def lote(*documentos: DocumentoDFe, max_nsu: int | None = None) -> RespostaDFe:
    return RespostaDFe(
        lote=Lote(documentos=documentos, max_nsu=max_nsu, ult_nsu=None), status=200
    )


class RepositorioFalso:
    def __init__(self) -> None:
        self.gravados: dict[int, tuple[str, str]] = {}
        self.checkpoints: list[int] = []

    def ja_tem(self, empresa_id: uuid.UUID, nsu: int) -> bool:
        return nsu in self.gravados

    def gravar(self, empresa_id, documento, xml_path, hash_) -> None:  # type: ignore[no-untyped-def]
        assert documento.nsu not in self.gravados, "gravou o mesmo NSU duas vezes"
        self.gravados[documento.nsu] = (xml_path, hash_)

    def atualizar_checkpoint(self, empresa_id: uuid.UUID, nsu: int) -> None:
        self.checkpoints.append(nsu)


@pytest.fixture
def repo() -> RepositorioFalso:
    return RepositorioFalso()


@pytest.fixture
def armazem(tmp_path: Path) -> ArmazenamentoLocal:
    return ArmazenamentoLocal(tmp_path)


def rodar(cliente, repo, armazem, ultimo_nsu: int = 0, **kw) -> ResultadoSync:  # type: ignore[no-untyped-def]
    return sincronizar_empresa(
        empresa_id=EMPRESA, ultimo_nsu=ultimo_nsu, cliente=cliente,
        repositorio=repo, armazenamento=armazem, **kw,
    )


# ------------------------------------------------------------ varredura ---


def test_percorre_ate_a_fila_esvaziar(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([
        lote(doc(1), doc(2)),
        lote(doc(3)),
        RespostaDFe(lote=None, status=204),
    ])
    r = rodar(cliente, repo, armazem)
    assert r.documentos_novos == 3
    assert r.nsu_final == 3
    assert cliente.pedidos == [1, 3, 4]


def test_comeca_do_checkpoint_e_nao_do_zero(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([lote(doc(101))])
    rodar(cliente, repo, armazem, ultimo_nsu=100)
    assert cliente.pedidos[0] == 101


def test_fila_vazia_de_cara(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    r = rodar(ClienteFalso([RespostaDFe(lote=None, status=204)]), repo, armazem)
    assert r.documentos_novos == 0 and r.status == "ok"


def test_para_no_max_nsu(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([lote(doc(1), doc(2), max_nsu=2), lote(doc(3))])
    r = rodar(cliente, repo, armazem)
    assert r.documentos_novos == 2
    assert cliente.pedidos == [1]


# --------------------------------------------------------- idempotência ---


def test_reprocessar_lote_nao_duplica(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    """UNIQUE (empresa, nsu) na spec §3.4 — aqui a regra antes do banco."""
    rodar(ClienteFalso([lote(doc(1), doc(2))]), repo, armazem)
    r = rodar(ClienteFalso([lote(doc(1), doc(2), doc(3))]), repo, armazem)
    assert r.documentos_repetidos == 2
    assert r.documentos_novos == 1
    assert sorted(repo.gravados) == [1, 2, 3]


def test_mesmo_xml_regravado_nao_corrompe(armazem) -> None:  # type: ignore[no-untyped-def]
    caminho = armazem.guardar("e/1.xml", b"<a/>")
    assert armazem.guardar("e/1.xml", b"<a/>") == caminho


def test_conteudo_diferente_na_mesma_chave_e_erro(armazem) -> None:  # type: ignore[no-untyped-def]
    armazem.guardar("e/1.xml", b"<a/>")
    with pytest.raises(ValueError, match="divergente"):
        armazem.guardar("e/1.xml", b"<b/>")


def test_xml_e_gravado_e_conferivel(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    documento = doc(1)
    rodar(ClienteFalso([lote(documento)]), repo, armazem)
    caminho, digest = repo.gravados[1]
    assert Path(caminho).read_bytes() == documento.xml
    assert digest == sha256(documento.xml)


# ----------------------------------------------------------- checkpoint ---


def test_checkpoint_por_lote_e_nao_no_fim(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([lote(doc(1)), lote(doc(2)), lote(doc(3))])
    rodar(cliente, repo, armazem)
    assert repo.checkpoints == [1, 2, 3], "checkpoint não avançou a cada lote"


def test_checkpoint_sobrevive_a_queda_no_meio(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    """Queda no terceiro lote não perde os dois primeiros."""
    cliente = ClienteFalso([
        lote(doc(1)), lote(doc(2)), AdnIndisponivel("caiu"),
    ])
    r = rodar(cliente, repo, armazem)
    assert r.status == "indisponivel"
    assert repo.checkpoints[-1] == 2
    assert sorted(repo.gravados) == [1, 2]


# -------------------------------------------------------------- lacunas ---


@pytest.mark.parametrize(
    "nsus,inicio,esperado",
    [
        ([1, 2, 3], 1, []),
        ([1, 3], 1, [(2, 2)]),
        ([1, 5], 1, [(2, 4)]),
        ([2, 3], 1, [(1, 1)]),
        ([], 1, []),
        ([3, 1, 2], 1, []),
        ([1, 4, 9], 1, [(2, 3), (5, 8)]),
    ],
)
def test_detectar_lacunas(nsus, inicio, esperado) -> None:  # type: ignore[no-untyped-def]
    assert detectar_lacunas(nsus, inicio) == esperado


def test_lacuna_vira_alerta_e_nao_silencio(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    r = rodar(ClienteFalso([lote(doc(1), doc(4))]), repo, armazem)
    assert r.lacunas == [(2, 3)]
    assert r.teve_lacuna


def test_sem_lacuna_quando_a_sequencia_e_continua(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    r = rodar(ClienteFalso([lote(doc(1), doc(2)), lote(doc(3))]), repo, armazem)
    assert r.lacunas == []


# ---------------------------------------------------------------- falhas ---


def test_recusa_do_adn_nao_repete_e_marca_status(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    r = rodar(ClienteFalso([AdnRecusou("certificado vencido")]), repo, armazem)
    assert r.status == "recusado"
    assert r.documentos_novos == 0


def test_nsu_que_nao_avanca_nao_vira_loop_infinito(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    """ADN devolvendo sempre o mesmo NSU travaria o worker para sempre."""
    cliente = ClienteFalso([lote(doc(1)), lote(doc(1)), lote(doc(1))])
    r = rodar(cliente, repo, armazem, ultimo_nsu=0)
    assert r.status == "erro"
    assert "não avançou" in (r.detalhe or "")


def test_limite_de_lotes_marca_parcial(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([lote(doc(n)) for n in range(1, 20)])
    r = rodar(cliente, repo, armazem, max_lotes=3)
    assert r.status == "parcial"
    assert r.lotes == 3
    assert repo.checkpoints[-1] == 3


def test_eventos_sao_capturados_junto_com_as_notas(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    cliente = ClienteFalso([
        lote(doc(1), doc(2, xml=b"<EventoNFSe/>", tipo="Evento"))
    ])
    r = rodar(cliente, repo, armazem)
    assert r.documentos_novos == 2


def test_callback_recebe_cada_documento_novo(repo, armazem) -> None:  # type: ignore[no-untyped-def]
    vistos: list[int] = []
    rodar(
        ClienteFalso([lote(doc(1), doc(2))]), repo, armazem,
        ao_persistir=lambda d: vistos.append(d.nsu),
    )
    assert vistos == [1, 2]

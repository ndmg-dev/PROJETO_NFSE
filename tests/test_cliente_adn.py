"""Cliente do ADN com o servidor mockado (spec §10, nível Integração).

LIMITE DESTES TESTES, EXPLÍCITO
O mock devolve a forma DECLARADA em app/adn/contrato.py, que ainda é hipótese.
Então estes testes provam que o backoff, o rate limit, a fila vazia e a
tradução funcionam — NÃO provam que o ADN devolve esses nomes de campo. Essa
prova só vem da produção restrita com certificado. É por isso que contrato.py
tem VERIFICADO = False e que extrair_lote levanta erro em vez de escolher um
candidato em silêncio.
"""

from __future__ import annotations

import ssl

import httpx
import pytest
import respx

from app.adn.cliente import (
    BACKOFF_MAX_S,
    MAX_TENTATIVAS,
    AdnIndisponivel,
    AdnRecusou,
    ClienteADN,
    espera_backoff,
)
from app.adn.contrato import ContratoDesconhecido, decodificar_conteudo

BASE = "https://adn.producaorestrita.nfse.gov.br"
XML = "<NFSe><infNFSe/></NFSe>"


class Relogio:
    """Substitui time.sleep: registra a espera em vez de dormir."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def cliente(relogio: Relogio) -> ClienteADN:
    return ClienteADN("restrita", ssl.create_default_context(), dormir=relogio)


def lote_json(*nsus: int, max_nsu: int | None = None) -> dict:
    corpo: dict = {
        "loteDFe": [
            {"NSU": n, "ArquivoXml": XML, "TipoDocumento": "NFSe"} for n in nsus
        ]
    }
    if max_nsu is not None:
        corpo["maxNSU"] = max_nsu
    return corpo


# ----------------------------------------------------------------- backoff ---


def test_backoff_respeita_retry_after() -> None:
    assert espera_backoff(0, "30") == 30.0


def test_backoff_limita_retry_after_absurdo() -> None:
    assert espera_backoff(0, "99999") == BACKOFF_MAX_S


def test_backoff_ignora_retry_after_em_data_http() -> None:
    assert 0.0 <= espera_backoff(0, "Wed, 21 Oct 2026 07:28:00 GMT") <= 1.0


def test_backoff_tem_jitter() -> None:
    """Sem jitter, N empresas voltam juntas e refazem o pico que causou o 429."""
    amostras = {espera_backoff(5) for _ in range(200)}
    assert len(amostras) > 1
    assert all(0.0 <= a <= BACKOFF_MAX_S for a in amostras)


def test_backoff_nunca_passa_do_teto() -> None:
    assert all(espera_backoff(t) <= BACKOFF_MAX_S for t in range(30))


# ------------------------------------------------------------- fila vazia ---


@respx.mock
def test_204_e_fila_vazia(cliente: ClienteADN) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(httpx.Response(204))
    assert cliente.buscar_dfe(1).lote is None


@respx.mock
def test_404_tratado_como_fim_da_fila(cliente: ClienteADN) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(httpx.Response(404))
    assert cliente.buscar_dfe(1).lote is None


@respx.mock
def test_corpo_vazio_e_fila_vazia(cliente: ClienteADN) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(httpx.Response(200, content=b""))
    assert cliente.buscar_dfe(1).lote is None


# ------------------------------------------------------------ rate limit ---


@respx.mock
def test_429_repete_e_respeita_retry_after(
    cliente: ClienteADN, relogio: Relogio
) -> None:
    rota = respx.get(f"{BASE}/contribuintes/DFe/1")
    rota.side_effect = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json=lote_json(1)),
    ]
    assert cliente.buscar_dfe(1).lote is not None
    assert relogio.esperas == [7.0]


@respx.mock
@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_repete(cliente: ClienteADN, relogio: Relogio, status: int) -> None:
    rota = respx.get(f"{BASE}/contribuintes/DFe/1")
    rota.side_effect = [httpx.Response(status), httpx.Response(200, json=lote_json(1))]
    assert cliente.buscar_dfe(1).lote is not None
    assert len(relogio.esperas) == 1


@respx.mock
def test_desiste_depois_do_maximo_de_tentativas(
    cliente: ClienteADN, relogio: Relogio
) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(httpx.Response(503))
    with pytest.raises(AdnIndisponivel, match="tentativas esgotadas"):
        cliente.buscar_dfe(1)
    assert len(relogio.esperas) == MAX_TENTATIVAS


@respx.mock
def test_falha_de_rede_tambem_repete(cliente: ClienteADN, relogio: Relogio) -> None:
    rota = respx.get(f"{BASE}/contribuintes/DFe/1")
    rota.side_effect = [
        httpx.ConnectError("sem rota"),
        httpx.Response(200, json=lote_json(1)),
    ]
    assert cliente.buscar_dfe(1).lote is not None


# ------------------------------------------------------- erro definitivo ---


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 403])
def test_erro_definitivo_nao_repete(
    cliente: ClienteADN, relogio: Relogio, status: int
) -> None:
    """Certificado errado ou vencido: repetir só gasta cota."""
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(
        httpx.Response(status, json={"erro": "CNPJ 07199546000162 sem permissão"})
    )
    with pytest.raises(AdnRecusou) as exc:
        cliente.buscar_dfe(1)
    assert relogio.esperas == []
    assert "07199546000162" not in str(exc.value), "vazou CNPJ na exceção"


@respx.mock
def test_resposta_nao_json_para_em_vez_de_chutar(cliente: ClienteADN) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(
        httpx.Response(200, content=b"<html>manutencao</html>")
    )
    with pytest.raises(ContratoDesconhecido):
        cliente.buscar_dfe(1)


@respx.mock
def test_contrato_diferente_do_esperado_para_e_mostra_as_chaves_reais(
    cliente: ClienteADN,
) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/1").mock(
        httpx.Response(200, json={"nomeQueNaoPrevimos": []})
    )
    with pytest.raises(ContratoDesconhecido) as exc:
        cliente.buscar_dfe(1)
    assert "nomeQueNaoPrevimos" in str(exc.value)


# ------------------------------------------------------------- tradução ---


@respx.mock
def test_traduz_o_lote(cliente: ClienteADN) -> None:
    respx.get(f"{BASE}/contribuintes/DFe/5").mock(
        httpx.Response(200, json=lote_json(5, 6, 7, max_nsu=99))
    )
    lote = cliente.buscar_dfe(5).lote
    assert lote is not None
    assert [d.nsu for d in lote.documentos] == [5, 6, 7]
    assert lote.maior_nsu == 7
    assert lote.max_nsu == 99
    assert lote.documentos[0].xml == XML.encode()


@respx.mock
def test_envia_cnpj_de_consulta_quando_informado(cliente: ClienteADN) -> None:
    rota = respx.get(f"{BASE}/contribuintes/DFe/1").mock(
        httpx.Response(200, json=lote_json(1))
    )
    cliente.buscar_dfe(1, cnpj_consulta="07199546000162")
    assert rota.calls.last.request.url.params["cnpj"] == "07199546000162"


def test_ambiente_invalido() -> None:
    with pytest.raises(ValueError, match="ambiente desconhecido"):
        ClienteADN("homologacao", ssl.create_default_context())


# ---------------------------------------------- decodificação do conteúdo ---


def test_decodifica_xml_puro() -> None:
    assert decodificar_conteudo("<NFSe/>") == b"<NFSe/>"


def test_decodifica_base64() -> None:
    import base64

    assert decodificar_conteudo(base64.b64encode(b"<NFSe/>").decode()) == b"<NFSe/>"


def test_decodifica_base64_com_gzip() -> None:
    import base64
    import gzip

    empacotado = base64.b64encode(gzip.compress(b"<NFSe/>")).decode()
    assert decodificar_conteudo(empacotado) == b"<NFSe/>"


def test_evento_detectado_pelo_tipo() -> None:
    from app.adn.contrato import DocumentoDFe

    assert DocumentoDFe(nsu=1, xml=b"<x/>", tipo="Evento").eh_evento
    assert not DocumentoDFe(nsu=1, xml=b"<x/>", tipo="NFSe").eh_evento


@respx.mock
def test_5xx_sem_corpo_nao_e_confundido_com_fila_vazia(
    cliente: ClienteADN, relogio: Relogio
) -> None:
    """Regressão: um 503 sem corpo era lido como fim da fila, e a varredura
    parava cedo perdendo notas em silêncio."""
    rota = respx.get(f"{BASE}/contribuintes/DFe/1")
    rota.side_effect = [
        httpx.Response(503, content=b""),
        httpx.Response(200, json=lote_json(1)),
    ]
    resposta = cliente.buscar_dfe(1)
    assert resposta.lote is not None, "503 vazio foi tratado como fila vazia"
    assert len(relogio.esperas) == 1

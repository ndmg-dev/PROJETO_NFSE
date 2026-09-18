"""Regressão de paridade com o portal — o critério de aceite da spec §10.

Pega as 78 notas reais do export da AB Engenharia de 08/2026, passa pelo nosso
gerador e compara o XLSX produzido com o arquivo original.

NOTA SOBRE O ESCOPO DA COMPARAÇÃO
O export do portal traz 60 colunas, mas preenche apenas 10 neste arquivo: as
outras 50 (ISSQN, base de cálculo, retenções, IBS/CBS) vêm vazias. Então
"diff zero linha a linha" só pode significar: mesmas 60 colunas na mesma
ordem, mesmas 78 linhas, e as 10 colunas preenchidas idênticas. Comparar as 50
vazias exigiria que o nosso relatório também as deixasse vazias — o que seria
um retrocesso, porque o XML traz esses dados.

PRECISÃO NO ARQUIVO
O XLSX não tem célula decimal: todo número vira double IEEE 754. Então a
garantia não é "o arquivo guarda Decimal", é "a soma acontece em Decimal e o
arquivo recebe um único valor já arredondado". O ruído do portal vem de
acumular em ponto flutuante, não de armazenar em ponto flutuante.

ORDEM DAS LINHAS
A spec pede ordenação por data de geração decrescente, e o portal exporta
assim. Mas a coluna traz só a data, sem hora, e várias notas compartilham o
mesmo dia — o desempate não é determinado por nada. Por isso comparamos o
conteúdo casando por chave de acesso, e verificamos a ordenação como
propriedade (não crescente), em vez de exigir uma ordem de empate arbitrária.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.core.dinheiro import formatar_brl
from app.domain.layout_relacao import (
    COLUNAS_PREENCHIDAS_NA_REFERENCIA,
    COLUNAS_RELACAO,
)
from app.reports.relacao_nfse import gerar_relacao
from tests.apoio_referencia import (
    CAMINHO_REFERENCIA,
    carregar_notas,
    ler_aba,
    resumo_da_referencia,
)

GERADO_EM = dt.datetime(2026, 9, 18, 15, 44, 6)


@pytest.fixture(scope="module")
def notas():  # type: ignore[no-untyped-def]
    if not CAMINHO_REFERENCIA.exists():
        pytest.skip(f"referência ausente: {CAMINHO_REFERENCIA}")
    return carregar_notas()


@pytest.fixture(scope="module")
def gerado(notas):  # type: ignore[no-untyped-def]
    buffer = BytesIO()
    gerar_relacao(notas, buffer, gerado_em=GERADO_EM)
    buffer.seek(0)
    return load_workbook(buffer)


# --------------------------------------------------------------- estrutura ---


def test_a_referencia_tem_as_78_notas(notas) -> None:  # type: ignore[no-untyped-def]
    assert len(notas) == 78


def test_layout_do_codigo_bate_com_o_arquivo_real() -> None:
    """Trava o contrato: se o portal mudar o layout, isto quebra."""
    cabecalho = [c for c in ler_aba(CAMINHO_REFERENCIA, "sheet1")[0] if c]
    assert tuple(cabecalho) == COLUNAS_RELACAO


def test_abas_com_os_mesmos_nomes(gerado) -> None:  # type: ignore[no-untyped-def]
    assert gerado.sheetnames == ["Relação", "Resumo"]


def test_mesmas_60_colunas_na_mesma_ordem(gerado) -> None:  # type: ignore[no-untyped-def]
    aba = gerado["Relação"]
    cabecalho = [c.value for c in aba[1]]
    assert cabecalho == list(COLUNAS_RELACAO)
    assert len(cabecalho) == 60


def test_mesma_quantidade_de_linhas(gerado, notas) -> None:  # type: ignore[no-untyped-def]
    assert gerado["Relação"].max_row == len(notas) + 1  # + cabeçalho


# ------------------------------------------------------------------ dados ---


def _linhas_por_chave(aba) -> dict[str, dict[str, object]]:  # type: ignore[no-untyped-def]
    cabecalho = [c.value for c in aba[1]]
    saida: dict[str, dict[str, object]] = {}
    for linha in aba.iter_rows(min_row=2, values_only=True):
        registro = dict(zip(cabecalho, linha, strict=True))
        saida[str(registro["Chave NFS-e"])] = registro
    return saida


def _referencia_por_chave() -> dict[str, dict[str, object]]:
    linhas = ler_aba(CAMINHO_REFERENCIA, "sheet1")
    cabecalho = [c or "" for c in linhas[0]]
    saida: dict[str, dict[str, object]] = {}
    for linha in linhas[1:]:
        registro = {
            nome: (linha[i] if i < len(linha) else None)
            for i, nome in enumerate(cabecalho)
        }
        chave = str(registro.get("Chave NFS-e") or "")
        if len(chave) == 50:
            saida[chave] = registro
    return saida


def test_mesmo_conjunto_de_chaves(gerado) -> None:  # type: ignore[no-untyped-def]
    assert set(_linhas_por_chave(gerado["Relação"])) == set(_referencia_por_chave())


@pytest.mark.parametrize("coluna", COLUNAS_PREENCHIDAS_NA_REFERENCIA)
def test_coluna_preenchida_bate_nota_a_nota(gerado, coluna: str) -> None:  # type: ignore[no-untyped-def]
    """Diff zero nas 10 colunas que a referência traz de fato."""
    nosso = _linhas_por_chave(gerado["Relação"])
    deles = _referencia_por_chave()

    divergentes: list[str] = []
    for chave, esperado in deles.items():
        a = _normalizar(nosso[chave][coluna], coluna)
        b = _normalizar(esperado[coluna], coluna)
        if a != b:
            divergentes.append(f"{chave}: gerado={a!r} referência={b!r}")

    assert not divergentes, f"{coluna}: {len(divergentes)} divergência(s)\n" + "\n".join(
        divergentes[:5]
    )


EPOCA_EXCEL = dt.date(1899, 12, 30)


def _normalizar(valor: object, coluna: str = "") -> object:
    """Compara conteúdo, não representação.

    O XLSX não tem tipo "data": guarda um serial numérico e um formato de
    exibição. Nas colunas de data convertemos os dois lados para `date`, senão
    compararíamos date contra Decimal('46265').
    """
    if valor is None or valor == "":
        return None
    if coluna.startswith("Data"):
        if isinstance(valor, dt.datetime):
            return valor.date()
        if isinstance(valor, dt.date):
            return valor
        return EPOCA_EXCEL + dt.timedelta(days=float(str(valor)))
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, Decimal | int | float):
        return Decimal(str(valor)).normalize()
    texto = str(valor).strip()
    try:
        return Decimal(texto).normalize()
    except (ArithmeticError, ValueError):
        return texto


def test_ordenacao_por_data_decrescente(gerado) -> None:  # type: ignore[no-untyped-def]
    aba = gerado["Relação"]
    indice = list(COLUNAS_RELACAO).index("Data Geração")
    datas = [
        linha[indice]
        for linha in aba.iter_rows(min_row=2, values_only=True)
        if linha[indice] is not None
    ]
    assert datas == sorted(datas, reverse=True)


def test_as_50_colunas_vazias_na_referencia_seguem_vazias(gerado) -> None:  # type: ignore[no-untyped-def]
    """Hoje o XML não alimenta essas colunas — quando alimentar, este teste
    quebra de propósito, e a mudança passa a ser consciente."""
    nosso = _linhas_por_chave(gerado["Relação"])
    vazias = set(COLUNAS_RELACAO) - set(COLUNAS_PREENCHIDAS_NA_REFERENCIA)
    preenchidas = {
        coluna
        for coluna in vazias
        for registro in nosso.values()
        if _normalizar(registro[coluna], coluna) is not None
    }
    assert not preenchidas, f"colunas inesperadamente preenchidas: {sorted(preenchidas)}"


# ----------------------------------------------------------------- resumo ---


def test_resumo_bate_com_o_do_portal(gerado) -> None:  # type: ignore[no-untyped-def]
    aba = gerado["Resumo"]
    nosso = {
        linha[0]: (linha[1], linha[2])
        for linha in aba.iter_rows(min_row=2, max_row=5, values_only=True)
    }
    deles = resumo_da_referencia()

    for situacao in ("Normal", "Cancelada", "Substituída", "Total"):
        qtd_nosso, valor_nosso = nosso[situacao]
        qtd_deles, valor_deles = deles[situacao]
        assert qtd_nosso == qtd_deles, situacao
        assert Decimal(str(valor_nosso)) == Decimal(str(valor_deles)).quantize(
            Decimal("0.01")
        ), situacao


def test_total_sem_ruido_de_ponto_flutuante(gerado) -> None:
    """A melhoria que a spec §5.1 pede: o portal imprime 198227.90999999997."""
    aba = gerado["Resumo"]
    total = next(
        linha[2]
        for linha in aba.iter_rows(min_row=2, max_row=5, values_only=True)
        if linha[0] == "Total"
    )
    # O XLSX guarda número como double IEEE 754 — não existe célula Decimal.
    # O que evita o ruído do portal não é o tipo da célula, é onde a soma
    # acontece: acumulamos em Decimal e gravamos UM valor já arredondado,
    # em vez de acumular em float. Ver a nota no topo deste arquivo.
    assert Decimal(str(total)) == Decimal("198227.91")
    assert formatar_brl(Decimal(str(total))) == "198.227,91"

    bruto = resumo_da_referencia()["Total"][1]
    assert str(bruto) == "198227.90999999997", "a referência mudou"


def test_rodape_de_geracao(gerado) -> None:  # type: ignore[no-untyped-def]
    aba = gerado["Resumo"]
    rodape = [
        linha
        for linha in aba.iter_rows(values_only=True)
        if linha and linha[0] == "Gerado em:"
    ]
    assert rodape and rodape[0][1] == "18/09/2026, 15:44:06"

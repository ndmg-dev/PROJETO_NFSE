"""Lê a planilha exportada do portal e a transforma em notas do nosso modelo.

Serve ao teste de paridade: o mesmo dado que o contador exporta hoje entra no
gerador, e o arquivo produzido é comparado com o original.
"""

from __future__ import annotations

import datetime as dt
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.core.dinheiro import dinheiro_opcional

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CAMINHO_REFERENCIA = Path("referencia/AB_ENGENHARIA_recebidas_082026.xlsx")
EPOCA_EXCEL = dt.date(1899, 12, 30)


def _indice(ref: str) -> int:
    letras = re.match(r"([A-Z]+)", ref)
    assert letras is not None
    n = 0
    for c in letras.group(1):
        n = n * 26 + ord(c) - 64
    return n - 1


def ler_aba(caminho: Path, aba: str) -> list[list[str | None]]:
    with zipfile.ZipFile(caminho) as z:
        raiz = ET.fromstring(z.read(f"xl/worksheets/{aba}.xml"))
    linhas: list[list[str | None]] = []
    for linha in raiz.iter(f"{{{NS}}}row"):
        celulas: dict[int, str | None] = {}
        for c in linha.iter(f"{{{NS}}}c"):
            ref = c.get("r")
            if ref is None:
                continue
            if c.get("t") == "inlineStr":
                bloco = c.find(f"{{{NS}}}is")
                valor: str | None = (
                    "".join(t.text or "" for t in bloco.iter(f"{{{NS}}}t"))
                    if bloco is not None
                    else ""
                )
            else:
                v = c.find(f"{{{NS}}}v")
                valor = v.text if v is not None else None
            celulas[_indice(ref)] = valor
        if celulas:
            linhas.append([celulas.get(i) for i in range(max(celulas) + 1)])
    return linhas


@dataclass
class NotaDaReferencia:
    """Espelha os atributos de `Nfse` que o relatório lê."""

    chave_acesso: str
    numero: str | None
    data_geracao: dt.datetime | None
    competencia: dt.date | None
    prestador_cnpj: str | None
    prestador_nome: str | None
    tomador_cnpj: str | None
    tomador_nome: str | None
    valor_servico: Decimal | None
    situacao: str
    simples_nacional: bool | None = None
    issqn_retido: bool | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, nome: str) -> None:
        # Colunas do layout que não existem na referência devolvem None em vez
        # de AttributeError — é exatamente o que o portal exporta nelas.
        return None


def _data(serial: str | None) -> dt.datetime | None:
    if not serial:
        return None
    return dt.datetime.combine(
        EPOCA_EXCEL + dt.timedelta(days=float(serial)), dt.time.min
    )


def _competencia(texto: str | None) -> dt.date | None:
    if not texto:
        return None
    mes, ano = texto.split("/")
    return dt.date(int(ano), int(mes), 1)


def carregar_notas(caminho: Path = CAMINHO_REFERENCIA) -> list[NotaDaReferencia]:
    linhas = ler_aba(caminho, "sheet1")
    cabecalho = [c or "" for c in linhas[0]]
    idx = {nome: i for i, nome in enumerate(cabecalho)}

    def campo(linha: list[str | None], nome: str) -> str | None:
        i = idx.get(nome, -1)
        return linha[i] if 0 <= i < len(linha) else None

    notas: list[NotaDaReferencia] = []
    for linha in linhas[1:]:
        chave = re.sub(r"\D", "", campo(linha, "Chave NFS-e") or "")
        if len(chave) != 50:  # pula o rodapé "TOTAL (78 notas)"
            continue
        notas.append(
            NotaDaReferencia(
                chave_acesso=chave,
                numero=campo(linha, "Número NFS-e"),
                data_geracao=_data(campo(linha, "Data Geração")),
                competencia=_competencia(campo(linha, "Competência")),
                prestador_cnpj=campo(linha, "CNPJ/CPF Prestador"),
                prestador_nome=campo(linha, "Nome Prestador"),
                tomador_cnpj=campo(linha, "CNPJ/CPF Tomador"),
                tomador_nome=campo(linha, "Nome Tomador"),
                valor_servico=dinheiro_opcional(campo(linha, "Valor do Serviço (R$)")),
                situacao=campo(linha, "Situação") or "Normal",
            )
        )
    return notas


def resumo_da_referencia(caminho: Path = CAMINHO_REFERENCIA) -> dict[str, Any]:
    linhas = ler_aba(caminho, "sheet2")
    dados: dict[str, Any] = {}
    for linha in linhas[1:]:
        if len(linha) >= 3 and linha[0] and linha[1] is not None:
            dados[linha[0]] = (int(linha[1]), Decimal(str(linha[2])))
    return dados

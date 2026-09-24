"""Texto de terceiros dentro de planilhas.

Nome do prestador, descrição do serviço e informações complementares vêm do XML
emitido pelo fornecedor: qualquer fornecedor que emita uma nota para o cliente
controla esse texto. Se ele começar com `=`, `+`, `-` ou `@`, o Excel pode
interpretá-lo como fórmula ao abrir o arquivo (injeção de fórmula / CSV
injection): de um HYPERLINK enganoso a execução de comando via DDE em versões
antigas. O contador abre esses arquivos por ofício.

Duas defesas, porque XLSX e CSV são diferentes:

  XLSX — a célula tem tipo. O openpyxl grava como fórmula toda string iniciada
         por `=`; forçamos o tipo texto e o valor sai idêntico, sem apóstrofo.
  CSV  — não há tipo de célula, então o único recurso é prefixar um apóstrofo
         (mitigação padrão da OWASP). O apóstrofo aparece no arquivo: é o preço
         de não executar fórmula alheia.

O CSV só recebe isso nas colunas de TEXTO. Prefixar um valor numérico como
`-5.00` o corromperia; número não é vetor de fórmula porque vem de `Decimal`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Protocol

GATILHOS_DE_FORMULA: Final = ("=", "+", "-", "@", "\t", "\r")


def neutralizar_formula(texto: str) -> str:
    """Prefixa apóstrofo se o texto puder ser lido como fórmula. Só para CSV."""
    return "'" + texto if texto.startswith(GATILHOS_DE_FORMULA) else texto


class CelulaXlsx(Protocol):
    data_type: str


def forcar_texto_literal(celulas: Iterable[CelulaXlsx]) -> int:
    """Converte em texto toda célula que o openpyxl teria gravado como fórmula.

    Devolve quantas converteu, para o chamador poder registrar.
    """
    convertidas = 0
    for celula in celulas:
        if celula.data_type == "f":
            celula.data_type = "s"
            convertidas += 1
    return convertidas

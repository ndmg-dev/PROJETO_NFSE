#!/usr/bin/env python3
"""Diff entre a captura do ADN e a planilha exportada do Portal Nacional.

Critério de aceite da Fase 0 (spec §12): AB Engenharia, 08/2026, como tomadora
— 78 notas, R$ 198.227,91.

Se não bater, este script serve para dizer POR QUE não bateu: ele quebra a
divergência por município (código IBGE nos 7 primeiros dígitos da chave de
acesso), que é a hipótese principal da spec §11.

Leitura do XLSX com a stdlib de propósito: a PoC só precisa LER a planilha, e
assim roda sem dependência instalada. openpyxl entra na Fase 1, para escrever
os relatórios (spec §5).

Uso:
    python poc/comparar_referencia.py --xml-dir poc/out/xml
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fase0_dfe import (  # noqa: E402
    Documento,
    interpretar_xml,
    moeda,
    normalizar_cnpj,
    para_decimal,
)

NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

COL_CHAVE = "Chave NFS-e"
COL_VALOR = "Valor do Serviço (R$)"
COL_PRESTADOR = "Nome Prestador"
COL_TOMADOR_CNPJ = "CNPJ/CPF Tomador"
COL_COMPETENCIA = "Competência"
COL_SITUACAO = "Situação"


@dataclass(frozen=True)
class LinhaReferencia:
    chave: str
    valor: Decimal
    prestador: str
    competencia: str
    situacao: str

    @property
    def ibge(self) -> str:
        return self.chave[:7]


# ------------------------------------------------------------ leitura xlsx ---


def _coluna_para_indice(ref: str) -> int:
    letras = re.match(r"([A-Z]+)", ref)
    assert letras is not None
    n = 0
    for c in letras.group(1):
        n = n * 26 + ord(c) - 64
    return n - 1


def _ler_aba(zf: zipfile.ZipFile, caminho: str) -> list[list[str | None]]:
    raiz = ET.fromstring(zf.read(caminho))
    linhas: list[list[str | None]] = []
    for linha in raiz.iter(f"{{{NS_SS}}}row"):
        celulas: dict[int, str | None] = {}
        for c in linha.iter(f"{{{NS_SS}}}c"):
            ref = c.get("r")
            if ref is None:
                continue
            if c.get("t") == "inlineStr":
                bloco = c.find(f"{{{NS_SS}}}is")
                valor = (
                    "".join(t.text or "" for t in bloco.iter(f"{{{NS_SS}}}t"))
                    if bloco is not None
                    else ""
                )
            else:
                v = c.find(f"{{{NS_SS}}}v")
                valor = v.text if v is not None else None
            celulas[_coluna_para_indice(ref)] = valor
        if celulas:
            linhas.append([celulas.get(i) for i in range(max(celulas) + 1)])
    return linhas


def carregar_referencia(caminho: Path) -> list[LinhaReferencia]:
    """Lê a aba 'Relação', descartando o rodapé de TOTAL."""
    with zipfile.ZipFile(caminho) as zf:
        linhas = _ler_aba(zf, "xl/worksheets/sheet1.xml")

    cabecalho = [c or "" for c in linhas[0]]
    idx = {nome: i for i, nome in enumerate(cabecalho)}
    faltando = {COL_CHAVE, COL_VALOR} - set(idx)
    if faltando:
        raise SystemExit(f"Colunas ausentes na referência: {sorted(faltando)}")

    def campo(linha: list[str | None], nome: str) -> str:
        i = idx.get(nome, -1)
        return (linha[i] or "") if 0 <= i < len(linha) else ""

    registros: list[LinhaReferencia] = []
    for linha in linhas[1:]:
        chave = re.sub(r"\D", "", campo(linha, COL_CHAVE))
        if len(chave) != 50:  # rodapé "TOTAL (78 notas)" e linhas em branco
            continue
        valor = para_decimal(campo(linha, COL_VALOR))
        registros.append(
            LinhaReferencia(
                chave=chave,
                valor=valor if valor is not None else Decimal(0),
                prestador=campo(linha, COL_PRESTADOR),
                competencia=campo(linha, COL_COMPETENCIA),
                situacao=campo(linha, COL_SITUACAO),
            )
        )
    return registros


# --------------------------------------------------------------- captura ---


def carregar_captura(dir_xml: Path) -> dict[str, Documento]:
    capturados: dict[str, Documento] = {}
    for arquivo in sorted(dir_xml.glob("*.xml")):
        doc = interpretar_xml(
            Documento(nsu=-1, xml=arquivo.read_bytes(), tipo_bruto=None)
        )
        if doc.chave_acesso:
            capturados[doc.chave_acesso] = doc
    return capturados


# ------------------------------------------------------------------ diff ---


def comparar(
    referencia: list[LinhaReferencia],
    capturados: dict[str, Documento],
    cnpj_alvo: str,
    competencia: str,
) -> int:
    ref_por_chave = {r.chave: r for r in referencia}
    chaves_ref = set(ref_por_chave)

    relevantes = {
        c: d
        for c, d in capturados.items()
        if not d.eh_evento
        and d.competencia == competencia
        and d.tomador_cnpj == cnpj_alvo
    }
    chaves_cap = set(relevantes)

    total_ref = sum((r.valor for r in referencia), Decimal(0))
    total_cap = sum(
        (d.valor_servico or Decimal(0) for d in relevantes.values()), Decimal(0)
    )

    print("=" * 66)
    print("DIFF — captura ADN × referência do Portal Nacional")
    print("=" * 66)
    print(f"Referência ....... {len(chaves_ref):4d} notas   R$ {moeda(total_ref)}")
    print(f"Capturado ........ {len(chaves_cap):4d} notas   R$ {moeda(total_cap)}")
    print(f"Delta ............ {len(chaves_cap) - len(chaves_ref):+4d} notas   "
          f"R$ {moeda(total_cap - total_ref)}")

    faltando = chaves_ref - chaves_cap
    sobrando = chaves_cap - chaves_ref

    if faltando:
        print(f"\n--- {len(faltando)} nota(s) na referência e AUSENTES no ADN ---")
        por_ibge: dict[str, list[LinhaReferencia]] = defaultdict(list)
        for c in faltando:
            por_ibge[ref_por_chave[c].ibge].append(ref_por_chave[c])
        print("Quebra por município (IBGE nos 7 primeiros dígitos da chave):")
        for ibge, itens in sorted(por_ibge.items(), key=lambda x: -len(x[1])):
            soma = sum((i.valor for i in itens), Decimal(0))
            print(f"  {ibge}  {len(itens):4d} nota(s)  R$ {moeda(soma):>14}")
        print("\nSe a ausência se concentra em poucos municípios, a causa é "
              "cobertura municipal (spec §11) — e a arquitetura muda.")
        for c in sorted(faltando)[:10]:
            r = ref_por_chave[c]
            print(f"  {c}  R$ {moeda(r.valor):>12}  {r.prestador[:40]}")
        if len(faltando) > 10:
            print(f"  ... e mais {len(faltando) - 10}")

    if sobrando:
        print(f"\n--- {len(sobrando)} nota(s) no ADN e AUSENTES na referência ---")
        for c in sorted(sobrando)[:10]:
            d = relevantes[c]
            print(f"  {c}  R$ {moeda(d.valor_servico or Decimal(0)):>12}")
        if len(sobrando) > 10:
            print(f"  ... e mais {len(sobrando) - 10}")

    divergentes = [
        (c, ref_por_chave[c].valor, relevantes[c].valor_servico)
        for c in chaves_ref & chaves_cap
        if relevantes[c].valor_servico != ref_por_chave[c].valor
    ]
    if divergentes:
        print(f"\n--- {len(divergentes)} nota(s) com valor divergente ---")
        for c, v_ref, v_cap in divergentes[:20]:
            print(f"  {c}  ref R$ {moeda(v_ref):>12}  adn R$ "
                  f"{moeda(v_cap or Decimal(0)):>12}")

    print("\n" + "=" * 66)
    if not faltando and not sobrando and not divergentes:
        print("APROVADO: diff zero contra a referência.")
        return 0
    print("REPROVADO: há divergência. NÃO ajuste o script para bater — "
          "investigue a causa (spec §12).")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--xml-dir", type=Path, default=Path("poc/out/xml"))
    p.add_argument("--referencia", type=Path,
                   default=Path("referencia/AB_ENGENHARIA_recebidas_082026.xlsx"))
    p.add_argument("--cnpj", default="07199546000162")
    p.add_argument("--competencia", default="2026-08")
    p.add_argument("--so-referencia", action="store_true",
                   help="apenas resume a planilha, sem exigir captura")
    args = p.parse_args(argv)

    referencia = carregar_referencia(args.referencia)

    if args.so_referencia:
        total = sum((r.valor for r in referencia), Decimal(0))
        print(f"Referência: {len(referencia)} notas, R$ {moeda(total)}")
        por_ibge: dict[str, list[LinhaReferencia]] = defaultdict(list)
        for r in referencia:
            por_ibge[r.ibge].append(r)
        print("\nPor município (IBGE):")
        for ibge, itens in sorted(por_ibge.items(), key=lambda x: -sum(
                (i.valor for i in x[1]), Decimal(0))):
            soma = sum((i.valor for i in itens), Decimal(0))
            print(f"  {ibge}  {len(itens):3d} nota(s)  R$ {moeda(soma):>14}")
        return 0

    if not args.xml_dir.is_dir():
        raise SystemExit(f"{args.xml_dir} não existe — rode fase0_dfe.py antes.")

    capturados = carregar_captura(args.xml_dir)
    if not capturados:
        raise SystemExit(
            f"Nenhum XML em {args.xml_dir}. A Fase 0 ainda não foi executada "
            "(falta o certificado A1)."
        )
    return comparar(capturados=capturados, referencia=referencia,
                    cnpj_alvo=normalizar_cnpj(args.cnpj),
                    competencia=args.competencia)


if __name__ == "__main__":
    sys.exit(main())

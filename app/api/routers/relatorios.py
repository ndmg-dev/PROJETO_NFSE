from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from app.api.deps import sessao
from app.core.planilha import neutralizar_formula
from app.db.models import Empresa, Nfse
from app.reports.relacao_nfse import gerar_relacao
from app.reports.retencoes import gerar_relatorio_retencoes

router = APIRouter(prefix="/empresas", tags=["relatorios"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _serializavel(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, date | datetime):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


def _nota_dict(nota: Nfse) -> dict[str, Any]:
    return {
        c.name: _serializavel(getattr(nota, c.name))
        for c in Nfse.__table__.columns
    }


def _nota_csv(nota: Nfse) -> dict[str, Any]:
    """Como _nota_dict, mas com o texto livre neutralizado contra fórmula.

    Só as colunas de texto: os números saem de Decimal e prefixá-los
    corromperia valores negativos.
    """
    linha: dict[str, Any] = {}
    for c in Nfse.__table__.columns:
        valor = getattr(nota, c.name)
        if isinstance(c.type, String) and isinstance(valor, str):
            linha[c.name] = neutralizar_formula(valor)
        else:
            linha[c.name] = _serializavel(valor)
    return linha


@router.get("/{empresa_id}/relatorio")
def relatorio(
    empresa_id: uuid.UUID, s: Session = Depends(sessao)
) -> StreamingResponse:
    """Gera a 'Relação de NFS-e' (XLSX) das notas da empresa. RLS já filtra
    por escritório; empresa de outro tenant chega como None -> 404."""
    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")

    notas = list(
        s.execute(select(Nfse).where(Nfse.empresa_id == empresa_id)).scalars()
    )
    buffer = BytesIO()
    gerar_relacao(notas, buffer)
    buffer.seek(0)

    nome = f"relacao_nfse_{empresa.cnpj}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/{empresa_id}/notas.zip")
def notas_zip(
    empresa_id: uuid.UUID, s: Session = Depends(sessao)
) -> StreamingResponse:
    """Empacota as notas da empresa num ZIP: um JSON por nota (dados da
    projeção nfse) + um notas.csv consolidado. RLS filtra por escritório."""
    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")

    notas = list(
        s.execute(
            select(Nfse).where(Nfse.empresa_id == empresa_id).order_by(Nfse.data_geracao)
        ).scalars()
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_:
        # um JSON por nota
        for nota in notas:
            dados = _nota_dict(nota)
            nome_arq = (nota.chave_acesso or nota.numero or str(nota.id)) + ".json"
            zip_.writestr(
                f"notas/{nome_arq}",
                json.dumps(dados, ensure_ascii=False, indent=2),
            )
        # CSV consolidado
        if notas:
            colunas = [c.name for c in Nfse.__table__.columns]
            texto = io.StringIO()
            escritor = csv.DictWriter(texto, fieldnames=colunas)
            escritor.writeheader()
            for nota in notas:
                escritor.writerow(_nota_csv(nota))
            zip_.writestr("notas.csv", texto.getvalue())
        else:
            zip_.writestr("LEIAME.txt", "Nenhuma nota cadastrada para esta empresa.\n")
    buffer.seek(0)

    nome = f"notas_{empresa.cnpj}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


Competencia = Annotated[
    str | None,
    Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="AAAA-MM", examples=["2026-08"]),
]


def _primeiro_dia(competencia: str) -> date:
    ano, mes = competencia.split("-")
    return date(int(ano), int(mes), 1)


@router.get("/{empresa_id}/retencoes")
def retencoes(
    empresa_id: uuid.UUID,
    competencia_de: Competencia = None,
    competencia_ate: Competencia = None,
    papel: Literal["prestador", "tomador"] | None = None,
    situacao: Annotated[list[Literal["Normal", "Cancelada", "Substituída"]] | None, Query()] = None,
    somente_divergentes: bool = False,
    s: Session = Depends(sessao),
) -> StreamingResponse:
    """Relatório de Retenções e Divergências de líquido (XLSX).

    Mostra, por nota, as retenções destacadas e compara o líquido declarado com o
    esperado. Por padrão só notas em situação Normal: retenção de nota cancelada
    não entra na conta. RLS filtra por escritório; empresa alheia chega como 404.
    """
    de = _primeiro_dia(competencia_de) if competencia_de else None
    ate = _primeiro_dia(competencia_ate) if competencia_ate else None
    if de and ate and de > ate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="competencia_de não pode ser posterior a competencia_ate",
        )

    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")

    situacoes = situacao or ["Normal"]
    filtro = [Nfse.empresa_id == empresa_id, Nfse.situacao.in_(situacoes)]
    if papel:
        filtro.append(Nfse.papel == papel)
    periodo = []
    if de:
        periodo.append(Nfse.competencia >= de)
    if ate:
        periodo.append(Nfse.competencia <= ate)

    notas = list(s.execute(select(Nfse).where(*filtro, *periodo)).scalars())

    # Nota sem competência não casa com nenhum filtro de período. Em vez de
    # sumir em silêncio, é contada no Resumo.
    sem_competencia = 0
    if periodo:
        sem_competencia = s.execute(
            select(func.count()).select_from(Nfse).where(*filtro, Nfse.competencia.is_(None))
        ).scalar_one()

    filtros = {
        "Empresa (CNPJ)": empresa.cnpj,
        "Competência de": competencia_de or "(sem limite)",
        "Competência até": competencia_ate or "(sem limite)",
        "Papel": papel or "(todos)",
        "Situação da NFS-e": ", ".join(situacoes),
    }
    buffer = BytesIO()
    gerar_relatorio_retencoes(
        notas, buffer, filtros=filtros, somente_divergentes=somente_divergentes,
        sem_competencia=sem_competencia,
    )
    buffer.seek(0)

    nome = f"retencoes_{empresa.cnpj}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )

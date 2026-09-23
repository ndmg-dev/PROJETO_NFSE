from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import sessao
from app.db.models import Empresa, Nfse
from app.reports.relacao_nfse import gerar_relacao

router = APIRouter(prefix="/empresas", tags=["relatorios"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _serializavel(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    return valor


def _nota_dict(nota: Nfse) -> dict[str, Any]:
    return {
        c.name: _serializavel(getattr(nota, c.name))
        for c in Nfse.__table__.columns
    }


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
                escritor.writerow(_nota_dict(nota))
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

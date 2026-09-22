from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, sessao
from app.api.schemas import EmpresaIn, EmpresaOut
from app.core.seguranca import Identidade
from app.db.models import Empresa

router = APIRouter(prefix="/empresas", tags=["empresas"])

# Upload de certificado foi removido por decisão de arquitetura (spec §3.3-A,
# 22/09/2026): o .pfx nunca sobe para o servidor. Ele permanece na estação do
# contador, e um agente local (Java + SunMSCAPI) o usa por lá. O casamento
# entre "empresa X" e "certificado Y da store" é feito pelo agente, pelo CNPJ
# raiz — não passa por esta API.


@router.get("", response_model=list[EmpresaOut])
def listar(
    s: Session = Depends(sessao), limite: int = 100, deslocamento: int = 0
) -> list[Empresa]:
    return list(
        s.execute(
            select(Empresa).order_by(Empresa.razao_social).limit(limite).offset(deslocamento)
        ).scalars()
    )


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: EmpresaIn,
    s: Session = Depends(sessao),
    identidade: Identidade = Depends(exigir_papel("admin", "operador")),
) -> Empresa:
    empresa = Empresa(
        id=uuid.uuid4(),
        escritorio_id=identidade.escritorio_id,
        cnpj=dados.cnpj,
        cnpj_raiz=dados.cnpj[:8],
        razao_social=dados.razao_social,
        inscricao_municipal=dados.inscricao_municipal,
        municipio_ibge=dados.municipio_ibge,
        regime_tributario=dados.regime_tributario,
        ultimo_nsu=0,
        sync_ativo=True,
    )
    s.add(empresa)
    try:
        s.flush()
    except IntegrityError:
        s.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="CNPJ já cadastrado"
        ) from None
    return empresa


@router.get("/{empresa_id}", response_model=EmpresaOut)
def obter(empresa_id: uuid.UUID, s: Session = Depends(sessao)) -> Empresa:
    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        # RLS já filtrou: empresa de outro escritório chega aqui como None e
        # sai como 404, sem revelar que o id existe.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")
    return empresa

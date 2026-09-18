from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adn.certificado import CertificadoError, ler_metadados
from app.api.deps import exigir_papel, sessao
from app.api.schemas import CertificadoOut, EmpresaIn, EmpresaOut
from app.core.cofre import cofre_padrao
from app.core.seguranca import Identidade
from app.db.models import Certificado, Empresa

router = APIRouter(prefix="/empresas", tags=["empresas"])

TAMANHO_MAXIMO_PFX = 512 * 1024


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


@router.post(
    "/{empresa_id}/certificado",
    response_model=CertificadoOut,
    status_code=status.HTTP_201_CREATED,
)
async def enviar_certificado(
    empresa_id: uuid.UUID,
    arquivo: UploadFile = File(...),
    senha: str = Form(...),
    s: Session = Depends(sessao),
    identidade: Identidade = Depends(exigir_papel("admin")),
) -> Certificado:
    """Recebe o .pfx e a senha. Nada disso volta na resposta (spec §8)."""
    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")

    conteudo = await arquivo.read(TAMANHO_MAXIMO_PFX + 1)
    if len(conteudo) > TAMANHO_MAXIMO_PFX:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="arquivo grande demais para um .pfx",
        )

    senha_bytes = senha.encode()
    try:
        metadados = ler_metadados(conteudo, senha_bytes)
    except CertificadoError:
        # str(exc) é sanitizado pelo módulo de certificado; ainda assim não
        # devolvemos nada além da categoria do erro.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="certificado inválido ou senha incorreta",
        ) from None

    if metadados.titular_cnpj and metadados.titular_cnpj[:8] != empresa.cnpj_raiz:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "o CNPJ raiz do certificado não corresponde ao da empresa; o ADN "
                "valida a raiz e recusaria a consulta"
            ),
        )
    if metadados.vencido_em(datetime.now(UTC).date()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="certificado vencido",
        )

    cofre = cofre_padrao()
    contexto = f"escritorio:{identidade.escritorio_id}:raiz:{empresa.cnpj_raiz}"
    certificado = Certificado(
        id=uuid.uuid4(),
        escritorio_id=identidade.escritorio_id,
        cnpj_raiz=empresa.cnpj_raiz,
        pfx_ciphered=cofre.guardar(conteudo, contexto).bytes_,
        senha_ciphered=cofre.guardar(senha_bytes, contexto).bytes_,
        titular_cnpj=metadados.titular_cnpj or None,
        titular_nome=metadados.titular_nome or None,
        valido_de=metadados.valido_de,
        valido_ate=metadados.valido_ate,
        ativo=True,
    )
    s.add(certificado)
    s.flush()
    return certificado


@router.get("/{empresa_id}/certificados", response_model=list[CertificadoOut])
def listar_certificados(
    empresa_id: uuid.UUID, s: Session = Depends(sessao)
) -> list[Certificado]:
    empresa = s.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="não encontrada")
    return list(
        s.execute(
            select(Certificado).where(Certificado.cnpj_raiz == empresa.cnpj_raiz)
        ).scalars()
    )

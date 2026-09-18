"""Contratos da API. O que não está aqui não sai pela rede."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

CNPJ_LIMPO = re.compile(r"^\d{14}$")


def limpar_cnpj(valor: str) -> str:
    return re.sub(r"\D", "", valor)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=8)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class EmpresaIn(BaseModel):
    cnpj: str
    razao_social: str = Field(min_length=1)
    inscricao_municipal: str | None = None
    municipio_ibge: str | None = Field(default=None, pattern=r"^\d{7}$")
    regime_tributario: str | None = None

    @field_validator("cnpj")
    @classmethod
    def _validar_cnpj(cls, v: str) -> str:
        limpo = limpar_cnpj(v)
        if not CNPJ_LIMPO.match(limpo):
            raise ValueError("CNPJ precisa ter 14 dígitos")
        return limpo


class EmpresaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cnpj: str
    cnpj_raiz: str
    razao_social: str
    inscricao_municipal: str | None
    municipio_ibge: str | None
    ultimo_nsu: int
    sync_ativo: bool
    ultimo_sync_at: datetime | None
    ultimo_sync_status: str | None


class CertificadoOut(BaseModel):
    """Só metadados. O .pfx e a senha NUNCA aparecem aqui (spec §8).

    Esta classe é a fronteira: se um campo de segredo for adicionado ao modelo
    do banco, ele não vaza por acidente, porque precisa ser declarado aqui.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cnpj_raiz: str
    titular_cnpj: str | None
    titular_nome: str | None
    valido_de: date | None
    valido_ate: date | None
    ativo: bool
    dias_para_vencer: int | None = None


class Problema(BaseModel):
    """RFC 7807 (spec §6)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None

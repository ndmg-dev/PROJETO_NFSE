"""Modelo relacional (spec §4).

Diferença deliberada em relação ao texto da spec, justificada no corpo:
`empresa.cnpj_raiz` — o ADN valida a raiz do CNPJ, não o CNPJ completo.

A tabela `certificado` da spec original foi removida por decisão de
arquitetura (§3.3-A, 22/09/2026): sem custódia central de .pfx.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# numeric(15,2) para dinheiro, numeric(7,4) para alíquota. Nunca double
# precision: `float` não entra no banco nem por acidente de migration.
Dinheiro = Numeric(15, 2, asdecimal=True)
Aliquota = Numeric(7, 4, asdecimal=True)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Escritorio(Base):
    __tablename__ = "escritorio"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("papel in ('admin','operador','leitura')", name="ck_usuario_papel"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    papel: Mapped[str] = mapped_column(Text, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (UniqueConstraint("escritorio_id", "cnpj"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    # DIFERENÇA DA SPEC §4: o ADN valida o CNPJ *raiz* entre o certificado e o
    # contribuinte consultado (Manual ADN v1.0, §1.1). Um A1 da matriz atende
    # todas as filiais. Guardar a raiz evita subir o mesmo .pfx N vezes e
    # revogar em N lugares.
    cnpj_raiz: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    razao_social: Mapped[str] = mapped_column(Text, nullable=False)
    inscricao_municipal: Mapped[str | None] = mapped_column(Text)
    municipio_ibge: Mapped[str | None] = mapped_column(String(7))
    regime_tributario: Mapped[str | None] = mapped_column(Text)
    ultimo_nsu: Mapped[int] = mapped_column(BigInteger, default=0)
    sync_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_sync_status: Mapped[str | None] = mapped_column(Text)


# Classe Certificado removida (spec §3.3-A, 22/09/2026): sem custódia central
# de .pfx. O certificado fica na estação do contador; o agente local o lê
# diretamente da store do Windows e nunca o envia para cá. Ver migration
# 0005_remove_certificado.


class DfeBruto(Base):
    """XML como fonte da verdade (spec §7). Nunca apagado, nunca sobrescrito."""

    __tablename__ = "dfe_bruto"
    __table_args__ = (UniqueConstraint("empresa_id", "nsu"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    nsu: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo_documento: Mapped[str | None] = mapped_column(Text)
    chave_acesso: Mapped[str | None] = mapped_column(String(50), index=True)
    xml_path: Mapped[str] = mapped_column(Text, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    versao_layout: Mapped[str | None] = mapped_column(Text)
    recebido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, default="pendente")
    tentativas_parse: Mapped[int] = mapped_column(Integer, default=0)
    erro_parse: Mapped[str | None] = mapped_column(Text)


class Nfse(Base):
    """Projeção reconstruível a partir do XML (spec §7)."""

    __tablename__ = "nfse"
    __table_args__ = (
        UniqueConstraint("empresa_id", "chave_acesso"),
        CheckConstraint("papel in ('prestador','tomador')", name="ck_nfse_papel"),
        Index("ix_nfse_competencia", "empresa_id", "competencia"),
        Index("ix_nfse_data_geracao", "empresa_id", "data_geracao"),
        Index("ix_nfse_prestador", "prestador_cnpj"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    chave_acesso: Mapped[str] = mapped_column(String(50), nullable=False)

    numero: Mapped[str | None] = mapped_column(Text)
    data_geracao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competencia: Mapped[date | None] = mapped_column(Date)
    papel: Mapped[str] = mapped_column(Text, nullable=False)

    prestador_cnpj: Mapped[str | None] = mapped_column(String(14))
    prestador_nome: Mapped[str | None] = mapped_column(Text)
    prestador_im: Mapped[str | None] = mapped_column(Text)
    tomador_cnpj: Mapped[str | None] = mapped_column(String(14))
    tomador_nome: Mapped[str | None] = mapped_column(Text)
    tomador_im: Mapped[str | None] = mapped_column(Text)
    municipio_incidencia: Mapped[str | None] = mapped_column(String(7))

    valor_servico: Mapped[Decimal | None] = mapped_column(Dinheiro)
    desconto_incondicionado: Mapped[Decimal | None] = mapped_column(Dinheiro)
    base_calculo: Mapped[Decimal | None] = mapped_column(Dinheiro)
    aliquota_issqn: Mapped[Decimal | None] = mapped_column(Aliquota)
    valor_issqn: Mapped[Decimal | None] = mapped_column(Dinheiro)
    issqn_retido: Mapped[bool | None] = mapped_column(Boolean)
    tributacao_issqn: Mapped[str | None] = mapped_column(Text)
    simples_nacional: Mapped[bool | None] = mapped_column(Boolean)
    cod_tributacao_nacional: Mapped[str | None] = mapped_column(Text)
    item_nbs: Mapped[str | None] = mapped_column(Text)
    descricao_servico: Mapped[str | None] = mapped_column(Text)

    # Reforma tributária (IBS/CBS)
    cst_ibs_cbs: Mapped[str | None] = mapped_column(Text)
    class_trib_ibs_cbs: Mapped[str | None] = mapped_column(Text)
    indicador_operacao: Mapped[str | None] = mapped_column(Text)
    bc_ibs_cbs: Mapped[Decimal | None] = mapped_column(Dinheiro)
    reemb_repasse: Mapped[Decimal | None] = mapped_column(Dinheiro)
    aliq_cbs: Mapped[Decimal | None] = mapped_column(Aliquota)
    red_aliq_cbs: Mapped[Decimal | None] = mapped_column(Aliquota)
    aliq_efetiva_cbs: Mapped[Decimal | None] = mapped_column(Aliquota)
    valor_cbs: Mapped[Decimal | None] = mapped_column(Dinheiro)
    aliq_ibs_estadual: Mapped[Decimal | None] = mapped_column(Aliquota)
    red_aliq_ibs_estadual: Mapped[Decimal | None] = mapped_column(Aliquota)
    aliq_efetiva_ibs_estadual: Mapped[Decimal | None] = mapped_column(Aliquota)
    valor_ibs_estadual: Mapped[Decimal | None] = mapped_column(Dinheiro)
    aliq_ibs_municipal: Mapped[Decimal | None] = mapped_column(Aliquota)
    red_aliq_ibs_municipal: Mapped[Decimal | None] = mapped_column(Aliquota)
    aliq_efetiva_ibs_municipal: Mapped[Decimal | None] = mapped_column(Aliquota)
    valor_ibs_municipal: Mapped[Decimal | None] = mapped_column(Dinheiro)
    valor_ibs_total: Mapped[Decimal | None] = mapped_column(Dinheiro)

    # Retenções federais
    sit_trib_pis_cofins: Mapped[str | None] = mapped_column(Text)
    bc_pis_cofins: Mapped[Decimal | None] = mapped_column(Dinheiro)
    pis_aliquota: Mapped[Decimal | None] = mapped_column(Aliquota)
    pis_debito: Mapped[Decimal | None] = mapped_column(Dinheiro)
    cofins_aliquota: Mapped[Decimal | None] = mapped_column(Aliquota)
    cofins_debito: Mapped[Decimal | None] = mapped_column(Dinheiro)
    descr_contrib_sociais: Mapped[str | None] = mapped_column(Text)
    irrf: Mapped[Decimal | None] = mapped_column(Dinheiro)
    contrib_sociais_retidas: Mapped[Decimal | None] = mapped_column(Dinheiro)
    contrib_previd_retida: Mapped[Decimal | None] = mapped_column(Dinheiro)
    pct_total_tributos_sn: Mapped[Decimal | None] = mapped_column(Aliquota)

    informacoes_complementares: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[str] = mapped_column(Text, nullable=False, default="Normal")
    dfe_bruto_id: Mapped[int | None] = mapped_column(ForeignKey("dfe_bruto.id"))

    eventos: Mapped[list[NfseEvento]] = relationship(back_populates="nfse")


class NfseEvento(Base):
    __tablename__ = "nfse_evento"
    __table_args__ = (UniqueConstraint("nfse_id", "tipo_evento", "data_evento"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    nfse_id: Mapped[int] = mapped_column(ForeignKey("nfse.id"), nullable=False)
    tipo_evento: Mapped[str] = mapped_column(Text, nullable=False)
    autor: Mapped[str | None] = mapped_column(Text)
    data_evento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_registro: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)
    xml_path: Mapped[str | None] = mapped_column(Text)

    nfse: Mapped[Nfse] = relationship(back_populates="eventos")


class Relatorio(Base):
    __tablename__ = "relatorio"

    id: Mapped[uuid.UUID] = _uuid_pk()
    escritorio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("escritorio.id"), nullable=False
    )
    tipo: Mapped[str | None] = mapped_column(Text)
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    formato: Mapped[str | None] = mapped_column(Text)
    filtros: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str | None] = mapped_column(Text)
    arquivo_path: Mapped[str | None] = mapped_column(Text)
    solicitado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    escritorio_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    recurso: Mapped[str | None] = mapped_column(Text)
    detalhe: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Tabelas com escopo de tenant — a migration cria política RLS para cada uma.
TABELAS_COM_RLS: tuple[str, ...] = (
    "usuario", "empresa", "dfe_bruto",
    "nfse", "nfse_evento", "relatorio",
)

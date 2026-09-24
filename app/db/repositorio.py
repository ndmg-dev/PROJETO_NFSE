"""Repositório concreto do XML bruto e do checkpoint (spec §3.4).

Implementa a interface `RepositorioDfe` de app/workers/sincronizacao.py, que até
aqui só tinha dublês de teste. Roda com a sessão do escritório: a RLS decide o
que cada consulta enxerga, não um filtro nosso.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.adn.contrato import DocumentoDFe
from app.db.models import DfeBruto, Empresa


class RepositorioDfeSql:
    def __init__(self, sessao: Session, escritorio_id: UUID) -> None:
        self._s = sessao
        self._escritorio_id = escritorio_id

    def ja_tem(self, empresa_id: UUID, nsu: int) -> bool:
        achado = self._s.execute(
            select(DfeBruto.id).where(DfeBruto.empresa_id == empresa_id, DfeBruto.nsu == nsu)
        ).first()
        return achado is not None

    def gravar(
        self, empresa_id: UUID, documento: DocumentoDFe, xml_path: str, hash_: str
    ) -> None:
        """Guarda a referência ao XML. A interpretação vem depois, na projeção:
        a chave de acesso e o resto saem do parser, não daqui."""
        self._s.add(
            DfeBruto(
                escritorio_id=self._escritorio_id,
                empresa_id=empresa_id,
                nsu=documento.nsu,
                tipo_documento="Evento" if documento.eh_evento else "NFSe",
                xml_path=xml_path,
                hash_sha256=hash_,
                status="pendente",
                tentativas_parse=0,
            )
        )
        self._s.flush()

    def atualizar_checkpoint(self, empresa_id: UUID, nsu: int) -> None:
        """Avança o NSU e faz commit: checkpoint é por lote, não no fim (§3.4).

        GREATEST porque o NSU nunca recua, mesmo que dois lotes cheguem fora de
        ordem. O commit fecha a transação; o escopo de tenant é reaplicado na
        seguinte pelo gancho de sessao_do_escritorio.
        """
        self._s.execute(
            update(Empresa)
            .where(Empresa.id == empresa_id)
            .values(ultimo_nsu=func.greatest(Empresa.ultimo_nsu, nsu), ultimo_sync_at=func.now())
        )
        self._s.commit()


def registrar_resultado_sync(sessao: Session, empresa_id: UUID, status: str) -> None:
    """Grava como a última sincronização terminou (ok, parcial, recusado...)."""
    sessao.execute(
        update(Empresa)
        .where(Empresa.id == empresa_id)
        .values(ultimo_sync_status=status, ultimo_sync_at=func.now())
    )
    sessao.commit()

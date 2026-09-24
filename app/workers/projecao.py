"""Projeção do XML bruto para as tabelas relacionais (spec §7).

O `dfe_bruto` é a fonte da verdade; `nfse` e `nfse_evento` são projeção
reconstruível. Este módulo lê os documentos pendentes, interpreta cada um com o
parser, decide com app/domain/projecao.py e grava.

Invariantes:
  - idempotência: reprocessar não duplica (upsert por empresa + chave);
  - um documento ruim não derruba os outros (savepoint por documento);
  - nada é descartado: o que não pôde ser projetado fica `erro` com o motivo e o
    XML preservado;
  - reprocessar TODA a base é possível: `situacao` vem dos eventos e o upsert
    não a sobrescreve; ela se reconstrói reaplicando os eventos em ordem de NSU.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.core.armazenamento import Armazenamento
from app.db.models import DfeBruto, Empresa, Nfse, NfseEvento
from app.domain.parser import XmlInvalido, parse_evento, parse_nfse
from app.domain.projecao import Rejeicao, decidir_evento, decidir_projecao

log = logging.getLogger(__name__)

MAX_TENTATIVAS_TRANSITORIAS = 3
COMMIT_A_CADA = 200

# Campos copiados do DTO do parser para a linha de nfse. Nomes idênticos nos dois
# lados; um teste confere que todos existem.
CAMPOS_PROJETADOS: tuple[str, ...] = (
    "numero", "data_geracao", "competencia",
    "prestador_cnpj", "prestador_nome", "prestador_im",
    "tomador_cnpj", "tomador_nome", "tomador_im",
    "municipio_incidencia", "valor_servico", "desconto_incondicionado",
    "base_calculo", "aliquota_issqn", "valor_issqn", "issqn_retido",
    "cod_tributacao_nacional", "item_nbs", "descricao_servico",
    "informacoes_complementares",
    "valor_liquido_declarado", "total_retencoes_declarado",
    "irrf", "contrib_sociais_retidas", "contrib_previd_retida",
    "pis_debito", "cofins_debito",
)


@dataclass
class ResumoProjecao:
    notas: int = 0
    eventos: int = 0
    rejeitados: int = 0  # ficaram em `erro`, com motivo
    orfaos: int = 0  # evento de nota que ainda não foi projetada; segue pendente
    falhas_transitorias: int = 0
    situacoes_alteradas: int = 0


def _rejeitar(doc: DfeBruto, motivo: str) -> None:
    doc.status = "erro"
    doc.tentativas_parse += 1
    doc.erro_parse = motivo


def _projetar_nota(sessao: Session, empresa: Empresa, doc: DfeBruto, xml: bytes) -> str | None:
    """Devolve o motivo da rejeição, ou None se projetou."""
    dto = parse_nfse(xml)
    decisao = decidir_projecao(dto, empresa.cnpj)
    if isinstance(decisao, Rejeicao):
        return decisao.motivo

    nota = decisao.dto
    valores: dict[str, object] = {
        "escritorio_id": empresa.escritorio_id,
        "empresa_id": empresa.id,
        "chave_acesso": nota.chave_acesso,
        "papel": decisao.papel,
        "situacao": "Normal",
        "dfe_bruto_id": doc.id,
        **{campo: getattr(nota, campo) for campo in CAMPOS_PROJETADOS},
    }
    insercao = pg_insert(Nfse).values(**valores)
    # `situacao` fica de fora do UPDATE: ela vem dos eventos, e reprocessar a
    # nota não pode ressuscitar uma nota cancelada.
    sobrescrever = {
        c: insercao.excluded[c]
        for c in [*CAMPOS_PROJETADOS, "papel", "dfe_bruto_id"]
    }
    sessao.execute(
        insercao.on_conflict_do_update(
            index_elements=["empresa_id", "chave_acesso"], set_=sobrescrever
        )
    )

    doc.chave_acesso = nota.chave_acesso
    doc.status = "processado"
    # Reuso de erro_parse como observação de qualidade: nota projetada, mas com
    # campo que o parser não achou ou documento que não coube.
    observacoes = [*decisao.avisos]
    if nota.campos_ausentes:
        observacoes.append("campos ausentes: " + ", ".join(nota.campos_ausentes))
    doc.erro_parse = "; ".join(observacoes) or None
    return None


def _projetar_evento(
    sessao: Session, empresa: Empresa, doc: DfeBruto, xml: bytes, resumo: ResumoProjecao
) -> str | None:
    """Devolve o motivo da rejeição, ou None. Evento órfão não é rejeição."""
    decisao = decidir_evento(parse_evento(xml))
    if isinstance(decisao, Rejeicao):
        return decisao.motivo

    nota = sessao.execute(
        select(Nfse).where(
            Nfse.empresa_id == empresa.id, Nfse.chave_acesso == decisao.chave_acesso
        )
    ).scalar_one_or_none()
    doc.chave_acesso = decisao.chave_acesso
    if nota is None:
        # A nota ainda não foi projetada (ou nunca chegou a esta empresa).
        # Continua pendente: a próxima projeção tenta de novo.
        doc.erro_parse = "nota do evento ainda não projetada"
        resumo.orfaos += 1
        return None

    # (nfse_id, tipo, data) não protege contra duplicata quando a data é NULL
    # (NULL != NULL no unique do Postgres), então a checagem é explícita.
    existente = sessao.execute(
        select(NfseEvento.id).where(
            NfseEvento.nfse_id == nota.id,
            NfseEvento.tipo_evento == decisao.tipo_evento,
            NfseEvento.data_evento.is_(None)
            if decisao.data_evento is None
            else NfseEvento.data_evento == decisao.data_evento,
        )
    ).first()
    if existente is None:
        sessao.add(
            NfseEvento(
                escritorio_id=empresa.escritorio_id,
                nfse_id=nota.id,
                tipo_evento=decisao.tipo_evento,
                autor=decisao.autor,
                data_evento=decisao.data_evento,
                motivo=decisao.motivo,
                xml_path=doc.xml_path,
            )
        )
    if decisao.nova_situacao and nota.situacao != decisao.nova_situacao:
        nota.situacao = decisao.nova_situacao
        resumo.situacoes_alteradas += 1

    doc.status = "processado"
    doc.erro_parse = None
    return None


def projetar_empresa(
    sessao: Session,
    *,
    empresa_id: UUID,
    armazenamento: Armazenamento,
    reprocessar_erros: bool = False,
) -> ResumoProjecao:
    """Projeta os documentos pendentes da empresa. Notas antes de eventos."""
    empresa = sessao.get(Empresa, empresa_id)
    if empresa is None:
        raise ValueError(f"empresa {empresa_id} não encontrada (ou de outro escritório)")

    estados = ("pendente", "erro") if reprocessar_erros else ("pendente",)
    documentos = list(
        sessao.execute(
            select(DfeBruto)
            .where(DfeBruto.empresa_id == empresa_id, DfeBruto.status.in_(estados))
            # NFSe antes de Evento, e por NSU dentro de cada grupo: um evento
            # sempre encontra a nota do mesmo lote, e vários eventos da mesma
            # nota reaplicam na ordem em que aconteceram.
            .order_by((DfeBruto.tipo_documento == "Evento"), DfeBruto.nsu)
        ).scalars()
    )

    resumo = ResumoProjecao()
    for indice, doc in enumerate(documentos, start=1):
        try:
            xml = armazenamento.ler(doc.xml_path)
        except OSError as exc:
            doc.tentativas_parse += 1
            doc.erro_parse = f"XML ilegível no armazenamento ({type(exc).__name__})"
            esgotou = doc.tentativas_parse >= MAX_TENTATIVAS_TRANSITORIAS
            doc.status = "erro" if esgotou else "pendente"
            resumo.falhas_transitorias += 1
            continue

        motivo: str | None
        try:
            with sessao.begin_nested():  # savepoint: um documento ruim não derruba o lote
                if doc.tipo_documento == "Evento":
                    motivo = _projetar_evento(sessao, empresa, doc, xml, resumo)
                else:
                    motivo = _projetar_nota(sessao, empresa, doc, xml)
        except XmlInvalido as exc:
            motivo = str(exc)
        except (DataError, IntegrityError) as exc:
            # O banco recusou os dados (campo maior que a coluna, por exemplo).
            # Determinístico: repetir não adianta.
            motivo = f"banco recusou os dados: {type(exc).__name__}"

        if motivo is not None:
            _rejeitar(doc, motivo)
            resumo.rejeitados += 1
            log.warning("documento rejeitado na projeção",
                        extra={"empresa_id": str(empresa_id), "nsu": doc.nsu, "motivo": motivo})
        elif doc.status == "processado":
            if doc.tipo_documento == "Evento":
                resumo.eventos += 1
            else:
                resumo.notas += 1

        if indice % COMMIT_A_CADA == 0:
            sessao.commit()

    sessao.commit()
    return resumo

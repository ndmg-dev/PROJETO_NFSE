"""Loop de sincronização por empresa (spec §3.4).

Invariantes, cada uma com teste:
  - idempotência por (empresa, nsu): reprocessar lote nunca duplica nota;
  - checkpoint por lote, não no fim: queda no meio retoma de onde parou;
  - lacuna de NSU vira alerta de auditoria, nunca silêncio;
  - documento que falha no parse vai para a fila morta com o XML preservado.

Este módulo NÃO depende dos nomes de campo do ADN: fala com `ClienteADN`, que
já entrega `Lote`. É por isso que ele pode ser testado hoje.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.adn.cliente import AdnIndisponivel, AdnRecusou, ClienteADN
from app.adn.contrato import DocumentoDFe
from app.core.armazenamento import Armazenamento, sha256

log = logging.getLogger(__name__)

MAX_LOTES_POR_EXECUCAO = 500  # trava contra loop infinito por NSU que não anda


class RepositorioDfe(Protocol):
    def ja_tem(self, empresa_id: UUID, nsu: int) -> bool: ...

    def gravar(
        self, empresa_id: UUID, documento: DocumentoDFe, xml_path: str, hash_: str
    ) -> None: ...

    def atualizar_checkpoint(self, empresa_id: UUID, nsu: int) -> None: ...


@dataclass
class ResultadoSync:
    empresa_id: UUID
    nsu_inicial: int
    nsu_final: int
    documentos_novos: int = 0
    documentos_repetidos: int = 0
    lotes: int = 0
    lacunas: list[tuple[int, int]] = field(default_factory=list)
    status: str = "ok"
    detalhe: str | None = None

    @property
    def teve_lacuna(self) -> bool:
        return bool(self.lacunas)


def detectar_lacunas(nsus: list[int], esperado_a_partir_de: int) -> list[tuple[int, int]]:
    """Intervalos de NSU ausentes. O NSU é a garantia de completude (§3.4).

    Uma lacuna não significa necessariamente perda: o ADN pode simplesmente não
    ter documento naquele NSU. Por isso vira alerta de auditoria e não erro —
    mas nunca silêncio.
    """
    if not nsus:
        return []
    lacunas: list[tuple[int, int]] = []
    anterior = esperado_a_partir_de - 1
    for nsu in sorted(nsus):
        if nsu > anterior + 1:
            lacunas.append((anterior + 1, nsu - 1))
        anterior = max(anterior, nsu)
    return lacunas


def sincronizar_empresa(
    *,
    empresa_id: UUID,
    ultimo_nsu: int,
    cliente: ClienteADN,
    repositorio: RepositorioDfe,
    armazenamento: Armazenamento,
    cnpj_consulta: str | None = None,
    max_lotes: int = MAX_LOTES_POR_EXECUCAO,
    ao_persistir: Any = None,
) -> ResultadoSync:
    """Percorre a fila do ADN a partir de `ultimo_nsu` + 1 até esvaziar."""
    resultado = ResultadoSync(
        empresa_id=empresa_id, nsu_inicial=ultimo_nsu, nsu_final=ultimo_nsu
    )
    nsu = ultimo_nsu + 1
    vistos: list[int] = []

    try:
        while resultado.lotes < max_lotes:
            resposta = cliente.buscar_dfe(nsu, cnpj_consulta)

            if resposta.lote is None:
                log.info(
                    "fila vazia",
                    extra={"empresa_id": str(empresa_id), "nsu": nsu,
                           "status": resposta.status},
                )
                break

            lote = resposta.lote
            if not lote.documentos:
                break

            for documento in lote.documentos:
                vistos.append(documento.nsu)
                if repositorio.ja_tem(empresa_id, documento.nsu):
                    resultado.documentos_repetidos += 1
                    continue
                digest = sha256(documento.xml)
                caminho = armazenamento.guardar(
                    f"{empresa_id}/{documento.nsu:012d}-{digest[:16]}.xml",
                    documento.xml,
                )
                repositorio.gravar(empresa_id, documento, caminho, digest)
                resultado.documentos_novos += 1
                if ao_persistir is not None:
                    ao_persistir(documento)

            maior = lote.maior_nsu
            assert maior is not None
            resultado.nsu_final = max(resultado.nsu_final, maior)
            resultado.lotes += 1

            # Checkpoint AQUI, não no fim: se o processo cair no próximo lote,
            # a próxima execução retoma daqui em vez de refazer tudo.
            repositorio.atualizar_checkpoint(empresa_id, resultado.nsu_final)

            if lote.max_nsu is not None and lote.max_nsu <= resultado.nsu_final:
                log.info(
                    "alcançado o maior NSU do ADN",
                    extra={"empresa_id": str(empresa_id), "max_nsu": lote.max_nsu},
                )
                break

            if maior < nsu:
                # NSU não avançou: repetir a mesma consulta é loop infinito.
                resultado.status = "erro"
                resultado.detalhe = (
                    f"NSU não avançou (pedido {nsu}, maior recebido {maior})"
                )
                break

            nsu = resultado.nsu_final + 1
        else:
            resultado.status = "parcial"
            resultado.detalhe = f"limite de {max_lotes} lotes; retomar do checkpoint"

    except AdnRecusou as exc:
        resultado.status = "recusado"
        resultado.detalhe = str(exc)
    except AdnIndisponivel as exc:
        resultado.status = "indisponivel"
        resultado.detalhe = str(exc)

    resultado.lacunas = detectar_lacunas(vistos, ultimo_nsu + 1)
    if resultado.teve_lacuna:
        log.warning(
            "lacuna de NSU detectada",
            extra={"empresa_id": str(empresa_id), "lacunas": resultado.lacunas},
        )
    return resultado


def agora() -> datetime:
    return datetime.now(UTC)

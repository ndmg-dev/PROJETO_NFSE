"""Cliente HTTP do ADN: mTLS, backoff exponencial com jitter, rate limit."""

from __future__ import annotations

import logging
import random
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import httpx

from app.adn.contrato import (
    STATUS_FILA_VAZIA,
    STATUS_RETENTAVEL,
    ContratoDesconhecido,
    Lote,
    extrair_lote,
)

log = logging.getLogger(__name__)

BASE_URLS: Final[dict[str, str]] = {
    "restrita": "https://adn.producaorestrita.nfse.gov.br",
    "producao": "https://adn.nfse.gov.br",
}
ROTA_DFE: Final = "/contribuintes/DFe/{nsu}"

BACKOFF_BASE_S: Final = 1.0
BACKOFF_FATOR: Final = 2.0
BACKOFF_MAX_S: Final = 60.0
MAX_TENTATIVAS: Final = 6
INTERVALO_ENTRE_LOTES_S: Final = 1.0


class AdnIndisponivel(RuntimeError):
    """Tentativas esgotadas. O worker reagenda; nada é perdido."""


class AdnRecusou(RuntimeError):
    """Erro definitivo do ADN (403, 400...). Repetir não adianta."""


@dataclass(frozen=True)
class RespostaDFe:
    lote: Lote | None  # None = fila vazia
    status: int


def espera_backoff(tentativa: int, retry_after: str | None = None) -> float:
    """Exponencial com jitter total. `Retry-After` do servidor tem prioridade.

    Jitter total (uniforme de 0 ao teto), e não jitter parcial: com N empresas
    sincronizando em paralelo, um backoff determinístico faz todas voltarem
    juntas e reconstruírem o mesmo pico que causou o 429.
    """
    if retry_after:
        try:
            return min(float(retry_after), BACKOFF_MAX_S)
        except ValueError:
            pass  # pode vir como data HTTP; cai no exponencial
    teto = min(BACKOFF_BASE_S * (BACKOFF_FATOR**tentativa), BACKOFF_MAX_S)
    return random.uniform(0.0, teto)


class ClienteADN:
    def __init__(
        self,
        ambiente: str,
        contexto_ssl: ssl.SSLContext,
        *,
        dormir: Callable[[float], None] = time.sleep,
        timeout: float = 60.0,
    ) -> None:
        if ambiente not in BASE_URLS:
            raise ValueError(f"ambiente desconhecido: {ambiente}")
        self._cliente = httpx.Client(
            base_url=BASE_URLS[ambiente],
            verify=contexto_ssl,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._dormir = dormir  # injetável: o teste não espera de verdade

    def __enter__(self) -> ClienteADN:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        self._cliente.close()

    def buscar_dfe(self, nsu: int, cnpj_consulta: str | None = None) -> RespostaDFe:
        params = {"cnpj": cnpj_consulta} if cnpj_consulta else None
        ultimo_status = 0

        for tentativa in range(MAX_TENTATIVAS):
            try:
                resposta = self._cliente.get(ROTA_DFE.format(nsu=nsu), params=params)
            except httpx.TransportError as exc:
                pausa = espera_backoff(tentativa)
                log.warning(
                    "falha de transporte no ADN",
                    extra={"nsu": nsu, "erro": type(exc).__name__, "pausa_s": pausa},
                )
                self._dormir(pausa)
                continue

            ultimo_status = resposta.status_code

            # ORDEM IMPORTA: o teste de "retentável" vem ANTES do de corpo
            # vazio. Um 503 costuma vir sem corpo; tratá-lo como fila vazia
            # faria a sincronização parar cedo achando que terminou, e perder
            # notas em silêncio — que é o pior defeito possível aqui.
            if resposta.status_code in STATUS_RETENTAVEL:
                pausa = espera_backoff(tentativa, resposta.headers.get("Retry-After"))
                log.warning(
                    "ADN pediu para esperar",
                    extra={
                        "nsu": nsu,
                        "status": resposta.status_code,
                        "pausa_s": pausa,
                        "tentativa": tentativa + 1,
                    },
                )
                self._dormir(pausa)
                continue

            if resposta.status_code in STATUS_FILA_VAZIA:
                return RespostaDFe(lote=None, status=resposta.status_code)

            if resposta.status_code >= 400:
                # 401/403 costuma ser certificado errado ou vencido; repetir só
                # gasta cota. O corpo NÃO vai para a exceção: pode citar CNPJ.
                raise AdnRecusou(
                    f"ADN recusou a consulta do NSU {nsu} com HTTP "
                    f"{resposta.status_code}."
                )

            # Corpo vazio só significa fila vazia num 2xx.
            if not resposta.content:
                return RespostaDFe(lote=None, status=resposta.status_code)

            try:
                payload = resposta.json()
            except ValueError:
                raise ContratoDesconhecido(
                    f"NSU {nsu}: resposta não é JSON (HTTP {resposta.status_code})."
                ) from None

            return RespostaDFe(lote=extrair_lote(payload), status=resposta.status_code)

        raise AdnIndisponivel(
            f"NSU {nsu}: {MAX_TENTATIVAS} tentativas esgotadas "
            f"(último status HTTP {ultimo_status})."
        )

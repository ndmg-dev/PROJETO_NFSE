"""Análise do valor líquido da NFS-e (spec §5.2, "Divergências e alertas").

O problema que motivou este módulo: a nota destaca IRRF, contribuições sociais,
PIS e COFINS, mas o "valor líquido" impresso é igual ao bruto e o "total das
retenções" fica em branco. Quem confere só o campo líquido conclui que não
houve retenção — enquanto a descrição do serviço manda pagar o valor já
descontado.

Por isso o sistema NUNCA confia no líquido declarado: calcula o esperado a
partir das retenções destacadas e compara.

DOIS CENÁRIOS, DE PROPÓSITO
  estrito  — abate só o que a nota rotula como retido: IRRF, contribuições
             sociais, contribuição previdenciária e ISSQN quando retido.
  ampliado — estrito + PIS e COFINS.

O DANFSe rotula PIS/COFINS como "Débito Apuração Própria" (tributo do próprio
prestador), não como "Retidas". Se foram de fato retidos é a discussão fiscal
em curso, e essa decisão é de quem assina a escrituração, não do código. O
módulo mostra os dois cenários e diz qual deles a descrição do serviço
corrobora, sem escolher um.

Módulo de domínio puro: sem I/O, sem ORM, sem rede.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, Protocol

from app.core.dinheiro import ValorInvalidoError, dinheiro, somar

# Um centavo absorve arredondamento de quem emitiu; mais que isso é divergência.
TOLERANCIA_PADRAO: Final = Decimal("0.01")

Situacao = Literal[
    "consistente",
    "retencao_nao_abatida",
    "liquido_acima_do_bruto",
    "liquido_abaixo_do_esperado",
    "indeterminado",
]
Cenario = Literal["estrito", "ampliado"]

_LIQUIDO_NA_DESCRICAO: Final = re.compile(
    r"valor\s+l[ií]quido\s*:?\s*(?:R\$)?\s*"
    r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})",
    re.IGNORECASE,
)


class NotaParaLiquido(Protocol):
    """O mínimo que a análise lê. Protocol em vez do ORM: testável sem banco."""

    @property
    def valor_servico(self) -> Decimal | None: ...
    @property
    def valor_liquido_declarado(self) -> Decimal | None: ...
    @property
    def total_retencoes_declarado(self) -> Decimal | None: ...
    @property
    def irrf(self) -> Decimal | None: ...
    @property
    def contrib_sociais_retidas(self) -> Decimal | None: ...
    @property
    def contrib_previd_retida(self) -> Decimal | None: ...
    @property
    def pis_debito(self) -> Decimal | None: ...
    @property
    def cofins_debito(self) -> Decimal | None: ...
    @property
    def valor_issqn(self) -> Decimal | None: ...
    @property
    def issqn_retido(self) -> bool | None: ...
    @property
    def descricao_servico(self) -> str | None: ...


@dataclass(frozen=True)
class AnaliseLiquido:
    situacao: Situacao
    bruto: Decimal | None
    liquido_declarado: Decimal | None
    retencoes_estritas: Decimal
    retencoes_ampliadas: Decimal
    liquido_estrito: Decimal | None
    liquido_ampliado: Decimal | None
    diferenca_estrita: Decimal | None  # declarado - estrito
    diferenca_ampliada: Decimal | None  # declarado - ampliado
    liquido_na_descricao: Decimal | None
    cenario_da_descricao: Cenario | None
    descricao_diverge_do_declarado: bool
    total_retencoes_omitido: bool
    avisos: tuple[str, ...]

    @property
    def requer_atencao(self) -> bool:
        """Vale mostrar no relatório de divergências?

        PIS/COFINS "de apuração própria" sozinhos NÃO disparam: sem retenção
        rotulada como tal, um líquido igual ao bruto é coerente com a nota.
        """
        return self.situacao in {
            "retencao_nao_abatida",
            "liquido_acima_do_bruto",
            "liquido_abaixo_do_esperado",
        } or self.descricao_diverge_do_declarado


def extrair_liquido_da_descricao(texto: str | None) -> Decimal | None:
    """Lê "Valor líquido: R$ 11.262,00" do texto livre da descrição.

    É INDÍCIO, não fato: texto livre, escrito à mão pelo emitente. Se aparecer
    mais de um valor diferente, devolve None em vez de escolher um.
    """
    if not texto:
        return None
    achados: set[Decimal] = set()
    for casamento in _LIQUIDO_NA_DESCRICAO.finditer(texto):
        try:
            achados.add(dinheiro(casamento.group(1)))
        except ValorInvalidoError:
            continue
    return next(iter(achados)) if len(achados) == 1 else None


def _proximo(a: Decimal, b: Decimal, tolerancia: Decimal) -> bool:
    return abs(a - b) <= tolerancia


def _presentes(valores: Iterable[Decimal | None]) -> list[Decimal]:
    return [v for v in valores if v is not None]


def analisar_liquido(
    nota: NotaParaLiquido, tolerancia: Decimal = TOLERANCIA_PADRAO
) -> AnaliseLiquido:
    avisos: list[str] = []

    estritos = _presentes(
        (nota.irrf, nota.contrib_sociais_retidas, nota.contrib_previd_retida)
    )
    if nota.issqn_retido is True:
        if nota.valor_issqn is None:
            avisos.append(
                "ISSQN marcado como retido, mas sem valor informado; "
                "não foi abatido no cálculo."
            )
        else:
            estritos.append(nota.valor_issqn)
    elif nota.issqn_retido is None and nota.valor_issqn is not None and nota.valor_issqn > 0:
        avisos.append(
            "Há valor de ISSQN, mas a nota não informa se foi retido; "
            "tratado como não retido."
        )

    retencoes_estritas = somar(estritos)
    retencoes_ampliadas = somar(
        [*estritos, *_presentes((nota.pis_debito, nota.cofins_debito))]
    )

    bruto = nota.valor_servico
    declarado = nota.valor_liquido_declarado
    liquido_estrito = bruto - retencoes_estritas if bruto is not None else None
    liquido_ampliado = bruto - retencoes_ampliadas if bruto is not None else None

    diferenca_estrita = (
        declarado - liquido_estrito
        if declarado is not None and liquido_estrito is not None
        else None
    )
    diferenca_ampliada = (
        declarado - liquido_ampliado
        if declarado is not None and liquido_ampliado is not None
        else None
    )

    situacao: Situacao
    if declarado is None or liquido_estrito is None or liquido_ampliado is None:
        situacao = "indeterminado"
    elif _proximo(declarado, liquido_estrito, tolerancia) or _proximo(
        declarado, liquido_ampliado, tolerancia
    ):
        # Bater com QUALQUER dos dois cenários é coerente: o emitente pode ter
        # tratado PIS/COFINS como retidos, e isso não é erro da nota.
        situacao = "consistente"
    elif declarado > liquido_estrito:
        situacao = (
            "retencao_nao_abatida"
            if retencoes_estritas > 0
            else "liquido_acima_do_bruto"
        )
    else:
        situacao = "liquido_abaixo_do_esperado"

    na_descricao = extrair_liquido_da_descricao(nota.descricao_servico)
    cenario: Cenario | None = None
    if na_descricao is not None and liquido_estrito is not None and liquido_ampliado is not None:
        if _proximo(na_descricao, liquido_estrito, tolerancia):
            cenario = "estrito"
        elif _proximo(na_descricao, liquido_ampliado, tolerancia):
            cenario = "ampliado"

    descricao_diverge = (
        na_descricao is not None
        and declarado is not None
        and not _proximo(na_descricao, declarado, tolerancia)
    )

    total = nota.total_retencoes_declarado
    total_omitido = retencoes_estritas > 0 and (total is None or total == 0)

    return AnaliseLiquido(
        situacao=situacao,
        bruto=bruto,
        liquido_declarado=declarado,
        retencoes_estritas=retencoes_estritas,
        retencoes_ampliadas=retencoes_ampliadas,
        liquido_estrito=liquido_estrito,
        liquido_ampliado=liquido_ampliado,
        diferenca_estrita=diferenca_estrita,
        diferenca_ampliada=diferenca_ampliada,
        liquido_na_descricao=na_descricao,
        cenario_da_descricao=cenario,
        descricao_diverge_do_declarado=descricao_diverge,
        total_retencoes_omitido=total_omitido,
        avisos=tuple(avisos),
    )

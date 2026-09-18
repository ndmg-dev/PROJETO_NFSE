"""Layout da aba `Relação` do export do Portal Nacional (spec §5.1).

As 60 colunas, na ordem exata do portal, e de onde cada uma sai no modelo.

A ordem é contrato: um teste confere esta tupla contra o arquivo de referência
real em `referencia/`. Se o portal mudar o layout, o teste quebra e a mudança é
consciente, em vez de aparecer como diff silencioso no relatório do cliente.
"""

from __future__ import annotations

from typing import Final

COLUNAS_RELACAO: Final[tuple[str, ...]] = (
    "Número NFS-e",
    "Data Geração",
    "Competência",
    "CNPJ/CPF Prestador",
    "Nome Prestador",
    "CNPJ/CPF Tomador",
    "Nome Tomador",
    "Valor do Serviço (R$)",
    "Insc. Municipal Emitente",
    "Simples Nacional",
    "DPS Nº",
    "DPS Série",
    "Situação NFS-e",
    "Tributação do ISSQN",
    "Município de Incidência",
    "Desconto Incond. (R$)",
    "Base de Cálculo (R$)",
    "Alíquota ISSQN (%)",
    "Valor do ISSQN (R$)",
    "Retenção ISSQN",
    "Cód. Tributação Nacional",
    "Item da NBS",
    "Descrição do Serviço",
    "CST IBS/CBS",
    "Class. Tributária IBS/CBS",
    "Indicador da Operação",
    "BC IBS/CBS (R$)",
    "Reemb./Repasse/Ressarc. (R$)",
    "Alíquota CBS (%)",
    "Red. Alíquota CBS (%)",
    "Alíq. Efetiva CBS (%)",
    "Valor CBS Total (R$)",
    "Alíquota IBS Estadual (%)",
    "Red. Alíq. IBS Estadual (%)",
    "Alíq. Efetiva IBS Estadual (%)",
    "Valor IBS Estadual (R$)",
    "Alíquota IBS Municipal (%)",
    "Red. Alíq. IBS Municipal (%)",
    "Alíq. Efetiva IBS Municipal (%)",
    "Valor IBS Municipal (R$)",
    "Valor IBS Total (R$)",
    "Sit. Trib. PIS/COFINS",
    "BC PIS/COFINS (R$)",
    "PIS - Alíquota (%)",
    "PIS - Débito (R$)",
    "COFINS - Alíquota (%)",
    "COFINS - Débito (R$)",
    "Descr. Contrib. Sociais Ret.",
    "IRRF (R$)",
    "Contrib. Sociais Ret. (R$)",
    "Contrib. Previd. Ret. (R$)",
    "% Total Tributos (SN)",
    "Insc. Municipal Tomador",
    "Informações Complementares",
    "Evento",
    "Autor do Evento",
    "Data do Evento",
    "Data Registro do Evento",
    "Situação",
    "Chave NFS-e",
)

# Coluna -> atributo do modelo Nfse. Coluna ausente aqui é derivada em
# `montar_linha` (evento, formatação) ou fica vazia por não existir no layout
# atual do XML.
# "DPS Nº" e "DPS Série" ficam fora: são campos da DPS (documento que origina
# a NFS-e), não da NFS-e, e o modelo não os guarda. Mapeá-los para `numero`
# seria inventar equivalência.
ORIGEM_NO_MODELO: Final[dict[str, str]] = {
    "Número NFS-e": "numero",
    "CNPJ/CPF Prestador": "prestador_cnpj",
    "Nome Prestador": "prestador_nome",
    "CNPJ/CPF Tomador": "tomador_cnpj",
    "Nome Tomador": "tomador_nome",
    "Valor do Serviço (R$)": "valor_servico",
    "Insc. Municipal Emitente": "prestador_im",
    "Tributação do ISSQN": "tributacao_issqn",
    "Município de Incidência": "municipio_incidencia",
    "Desconto Incond. (R$)": "desconto_incondicionado",
    "Base de Cálculo (R$)": "base_calculo",
    "Alíquota ISSQN (%)": "aliquota_issqn",
    "Valor do ISSQN (R$)": "valor_issqn",
    "Cód. Tributação Nacional": "cod_tributacao_nacional",
    "Item da NBS": "item_nbs",
    "Descrição do Serviço": "descricao_servico",
    "CST IBS/CBS": "cst_ibs_cbs",
    "Class. Tributária IBS/CBS": "class_trib_ibs_cbs",
    "Indicador da Operação": "indicador_operacao",
    "BC IBS/CBS (R$)": "bc_ibs_cbs",
    "Reemb./Repasse/Ressarc. (R$)": "reemb_repasse",
    "Alíquota CBS (%)": "aliq_cbs",
    "Red. Alíquota CBS (%)": "red_aliq_cbs",
    "Alíq. Efetiva CBS (%)": "aliq_efetiva_cbs",
    "Valor CBS Total (R$)": "valor_cbs",
    "Alíquota IBS Estadual (%)": "aliq_ibs_estadual",
    "Red. Alíq. IBS Estadual (%)": "red_aliq_ibs_estadual",
    "Alíq. Efetiva IBS Estadual (%)": "aliq_efetiva_ibs_estadual",
    "Valor IBS Estadual (R$)": "valor_ibs_estadual",
    "Alíquota IBS Municipal (%)": "aliq_ibs_municipal",
    "Red. Alíq. IBS Municipal (%)": "red_aliq_ibs_municipal",
    "Alíq. Efetiva IBS Municipal (%)": "aliq_efetiva_ibs_municipal",
    "Valor IBS Municipal (R$)": "valor_ibs_municipal",
    "Valor IBS Total (R$)": "valor_ibs_total",
    "Sit. Trib. PIS/COFINS": "sit_trib_pis_cofins",
    "BC PIS/COFINS (R$)": "bc_pis_cofins",
    "PIS - Alíquota (%)": "pis_aliquota",
    "PIS - Débito (R$)": "pis_debito",
    "COFINS - Alíquota (%)": "cofins_aliquota",
    "COFINS - Débito (R$)": "cofins_debito",
    "Descr. Contrib. Sociais Ret.": "descr_contrib_sociais",
    "IRRF (R$)": "irrf",
    "Contrib. Sociais Ret. (R$)": "contrib_sociais_retidas",
    "Contrib. Previd. Ret. (R$)": "contrib_previd_retida",
    "% Total Tributos (SN)": "pct_total_tributos_sn",
    "Insc. Municipal Tomador": "tomador_im",
    "Informações Complementares": "informacoes_complementares",
    "Situação": "situacao",
    "Chave NFS-e": "chave_acesso",
}

# Colunas que o portal preenche de fato no export de referência. As outras 50
# vêm vazias no arquivo do cliente — ver a nota em tests/test_paridade.py.
COLUNAS_PREENCHIDAS_NA_REFERENCIA: Final[tuple[str, ...]] = (
    "Número NFS-e",
    "Data Geração",
    "Competência",
    "CNPJ/CPF Prestador",
    "Nome Prestador",
    "CNPJ/CPF Tomador",
    "Nome Tomador",
    "Valor do Serviço (R$)",
    "Situação",
    "Chave NFS-e",
)

SITUACOES: Final[tuple[str, ...]] = ("Normal", "Cancelada", "Substituída")

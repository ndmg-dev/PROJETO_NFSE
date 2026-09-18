#!/usr/bin/env python3
"""Fase 0 — prova de conceito da captura de NFS-e nacional via ADN.

Objetivo (spec §12): provar que `GET /contribuintes/DFe/{NSU}` devolve o mesmo
conjunto de notas que o Portal Nacional exporta em planilha.

Script isolado: sem framework, sem banco, sem estado além dos arquivos gravados
em `poc/out/`.

Uso:
    python poc/fase0_dfe.py --ambiente restrita --pfx ~/certs/ab.pfx

Descoberta de contrato (rodar primeiro, uma vez):
    python poc/fase0_dfe.py --ambiente restrita --pfx ... --dump-contrato
    python poc/fase0_dfe.py --ambiente restrita --pfx ... --inspecionar-xml

Ver o bloco HIPÓTESES abaixo antes de confiar em qualquer número impresso.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import gzip
import hashlib
import json
import os
import random
import re
import ssl
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Ambientes (spec §3.1)
# ---------------------------------------------------------------------------

BASE_URLS: dict[str, str] = {
    "restrita": "https://adn.producaorestrita.nfse.gov.br",
    "producao": "https://adn.nfse.gov.br",
}

ROTA_DFE = "/contribuintes/DFe/{nsu}"

# ---------------------------------------------------------------------------
# HIPÓTESES — o contrato do ADN NÃO está documentado
# ---------------------------------------------------------------------------
# O Manual dos Contribuintes v1.0 (12/02/2026) descreve apenas a existência de
# GET /DFe/{NSU}; não fixa nomes de campo, paginação, tamanho de lote, rate
# limit nem o código de fila vazia. A spec §3.2 marca tudo isso como "a validar
# em homologação".
#
# As listas abaixo são CANDIDATOS, não fatos. O script nunca escolhe um
# silenciosamente: se nenhum candidato casar, ele aborta com as chaves reais da
# resposta (ContratoDesconhecido). Depois da primeira execução com certificado,
# substitua cada lista pelo nome único e verdadeiro e apague o resto.
#
# STATUS: NÃO VERIFICADO — nenhuma execução real contra o ADN até aqui.

CANDIDATOS_LOTE: tuple[str, ...] = ("loteDFe", "LoteDFe", "documentos", "DFe", "lote")
CANDIDATOS_NSU_DOC: tuple[str, ...] = ("NSU", "nsu")
CANDIDATOS_CONTEUDO: tuple[str, ...] = ("ArquivoXml", "arquivoXml", "XmlDFe", "xml", "documento")
CANDIDATOS_TIPO: tuple[str, ...] = ("TipoDocumento", "tipoDocumento", "tipo", "schema")
CANDIDATOS_ULTIMO_NSU: tuple[str, ...] = ("ultNSU", "ultimoNSU", "UltimoNSU")
CANDIDATOS_MAX_NSU: tuple[str, ...] = ("maxNSU", "MaxNSU", "maximoNSU")

# Layout do XML da NFS-e nacional. Também candidatos: confirmar contra o XSD
# oficial e contra o primeiro XML real (use --inspecionar-xml).
TAGS_COMPETENCIA: tuple[str, ...] = ("dCompet", "Competencia", "competencia")
TAGS_VALOR_SERVICO: tuple[str, ...] = ("vServ", "ValorServico", "vServPrest")
TAGS_TOMADOR: tuple[str, ...] = ("toma", "Tomador", "tomador")
TAGS_CNPJ: tuple[str, ...] = ("CNPJ", "Cnpj", "cnpj")

# ---------------------------------------------------------------------------
# Política de retry (spec §3.4)
# ---------------------------------------------------------------------------

BACKOFF_BASE_S = 1.0
BACKOFF_FATOR = 2.0
BACKOFF_MAX_S = 60.0
MAX_TENTATIVAS = 6
INTERVALO_ENTRE_LOTES_S = 1.0
STATUS_RETENTAVEIS = frozenset({429, 500, 502, 503, 504})


class ContratoDesconhecido(RuntimeError):
    """A resposta do ADN não casou com nenhuma hipótese. Nunca chute: pare."""


class FalhaPermanente(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Certificado A1 (spec §3.3 e §8)
# ---------------------------------------------------------------------------


def _dir_tmpfs() -> Path:
    """Diretório em memória para o PEM temporário. Nunca em disco persistente."""
    for candidato in ("/dev/shm", "/run/user/%d" % os.getuid()):
        p = Path(candidato)
        if p.is_dir() and os.access(p, os.W_OK):
            return p
    raise FalhaPermanente(
        "Nenhum tmpfs gravável encontrado (/dev/shm). Recuso-me a escrever a "
        "chave privada em disco persistente."
    )


@dataclass
class Certificado:
    """Metadados públicos do A1. A senha e a chave privada não moram aqui."""

    titular_cnpj: str
    titular_nome: str
    valido_de: str
    valido_ate: str

    @property
    def cnpj_raiz(self) -> str:
        return self.titular_cnpj[:8]


def carregar_certificado(
    pfx_bytes: bytes, senha: bytes
) -> tuple[ssl.SSLContext, Certificado, Path]:
    """Monta o SSLContext mTLS a partir do .pfx.

    Devolve também o caminho do PEM em tmpfs — o chamador DEVE apagá-lo num
    `finally`. A senha nunca é registrada, nem em exceção.
    """
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        pkcs12,
    )

    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(pfx_bytes, senha)
    except Exception as exc:  # noqa: BLE001 — mensagem sanitizada de propósito
        raise FalhaPermanente(
            f"Não foi possível abrir o .pfx ({type(exc).__name__}). "
            "Senha incorreta ou arquivo corrompido."
        ) from None

    if chave is None or cert is None:
        raise FalhaPermanente("O .pfx não contém par chave/certificado utilizável.")

    tmpdir = _dir_tmpfs()
    fd, nome = tempfile.mkstemp(suffix=".pem", dir=tmpdir)
    caminho = Path(nome)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(cert.public_bytes(Encoding.PEM))
            for c in cadeia or []:
                f.write(c.public_bytes(Encoding.PEM))
            f.write(
                chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
            )
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(caminho))
    except BaseException:
        caminho.unlink(missing_ok=True)
        raise

    return ctx, _metadados(cert), caminho


def _metadados(cert: Any) -> Certificado:
    from cryptography.x509.oid import NameOID

    def attr(oid: Any) -> str:
        vals = cert.subject.get_attributes_for_oid(oid)
        return str(vals[0].value) if vals else ""

    nome_completo = attr(NameOID.COMMON_NAME)
    # O CN do e-CNPJ costuma ser "RAZAO SOCIAL:CNPJ". Extraímos o primeiro
    # bloco de 14 dígitos que aparecer no subject.
    digitos = re.findall(r"\d{14}", nome_completo)
    cnpj = digitos[0] if digitos else ""
    return Certificado(
        titular_cnpj=cnpj,
        titular_nome=nome_completo.split(":")[0],
        valido_de=cert.not_valid_before_utc.date().isoformat(),
        valido_ate=cert.not_valid_after_utc.date().isoformat(),
    )


# ---------------------------------------------------------------------------
# Helpers de contrato
# ---------------------------------------------------------------------------


def primeiro_presente(d: dict[str, Any], candidatos: tuple[str, ...]) -> str | None:
    for c in candidatos:
        if c in d:
            return c
    return None


def exigir_chave(
    d: dict[str, Any], candidatos: tuple[str, ...], papel: str, dump: Path | None
) -> str:
    achada = primeiro_presente(d, candidatos)
    if achada is not None:
        return achada
    raise ContratoDesconhecido(
        f"Não encontrei a chave de {papel} na resposta do ADN.\n"
        f"  candidatos testados: {list(candidatos)}\n"
        f"  chaves reais:        {sorted(d.keys())}\n"
        + (f"  resposta crua salva em: {dump}\n" if dump else "")
        + "Atualize o bloco HIPÓTESES no topo de poc/fase0_dfe.py com o nome real."
    )


def decodificar_conteudo(valor: str) -> bytes:
    """Converte o campo de conteúdo do documento em XML bruto.

    Detecção por conteúdo, não por nome de campo: base64 → gzip → texto.
    """
    bruto: bytes
    try:
        bruto = base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError):
        return valor.encode("utf-8")

    if bruto[:2] == b"\x1f\x8b":
        return gzip.decompress(bruto)
    if bruto.lstrip()[:1] in (b"<", b"\xef"):
        return bruto
    return valor.encode("utf-8")


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def achar_texto(raiz: ET.Element, tags: tuple[str, ...]) -> str | None:
    """Busca o primeiro elemento cujo nome local casa, ignorando namespace.

    A spec §6 exige tolerância a namespace inesperado — por isso não usamos
    XPath com prefixo fixo.
    """
    alvo = {t.lower() for t in tags}
    for el in raiz.iter():
        if localname(el.tag).lower() in alvo and el.text and el.text.strip():
            return el.text.strip()
    return None


def achar_elemento(raiz: ET.Element, tags: tuple[str, ...]) -> ET.Element | None:
    alvo = {t.lower() for t in tags}
    for el in raiz.iter():
        if localname(el.tag).lower() in alvo:
            return el
    return None


def extrair_chave_acesso(raiz: ET.Element, xml: bytes) -> str | None:
    """A chave da NFS-e nacional tem 50 dígitos. Procura por conteúdo."""
    for el in raiz.iter():
        for valor in el.attrib.values():
            so_digitos = re.sub(r"\D", "", valor)
            if len(so_digitos) == 50:
                return so_digitos
        if el.text:
            t = el.text.strip()
            if len(t) == 50 and t.isdigit():
                return t
    achado = re.search(rb"\b\d{50}\b", xml)
    return achado.group(0).decode() if achado else None


def para_decimal(texto: str | None) -> Decimal | None:
    """Dinheiro é Decimal, sempre (regra 4). Nunca float em nenhum caminho."""
    if texto is None:
        return None
    limpo = texto.strip().replace(" ", "")
    if not limpo:
        return None
    if "," in limpo:  # formato pt-BR: 1.234,56
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def normalizar_cnpj(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def normalizar_competencia(texto: str | None) -> str | None:
    """Devolve AAAA-MM a partir de 'AAAA-MM-DD', 'MM/AAAA' ou 'AAAA-MM'."""
    if not texto:
        return None
    t = texto.strip()
    if m := re.match(r"^(\d{4})-(\d{2})", t):
        return f"{m.group(1)}-{m.group(2)}"
    if m := re.match(r"^(\d{2})/(\d{4})$", t):
        return f"{m.group(2)}-{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# Documento capturado
# ---------------------------------------------------------------------------


@dataclass
class Documento:
    nsu: int
    xml: bytes
    tipo_bruto: str | None
    chave_acesso: str | None = None
    eh_evento: bool = False
    competencia: str | None = None
    valor_servico: Decimal | None = None
    tomador_cnpj: str = ""
    campos_faltando: list[str] = field(default_factory=list)

    @property
    def nome_arquivo(self) -> str:
        if self.chave_acesso:
            return f"{self.chave_acesso}.xml"
        digest = hashlib.sha256(self.xml).hexdigest()[:16]
        return f"sem-chave-nsu{self.nsu:012d}-{digest}.xml"


def interpretar_xml(doc: Documento) -> Documento:
    """Extrai os campos do resumo. Marca o que não achou, em vez de inventar."""
    try:
        raiz = ET.fromstring(doc.xml)
    except ET.ParseError as exc:
        doc.campos_faltando.append(f"xml-invalido:{exc}")
        return doc

    doc.chave_acesso = extrair_chave_acesso(raiz, doc.xml)

    nomes = {localname(el.tag).lower() for el in raiz.iter()}
    if doc.tipo_bruto:
        doc.eh_evento = "evento" in doc.tipo_bruto.lower()
    else:
        doc.eh_evento = any("evento" in n for n in nomes)

    if doc.eh_evento:
        return doc

    doc.competencia = normalizar_competencia(achar_texto(raiz, TAGS_COMPETENCIA))
    if doc.competencia is None:
        doc.campos_faltando.append("competencia")

    doc.valor_servico = para_decimal(achar_texto(raiz, TAGS_VALOR_SERVICO))
    if doc.valor_servico is None:
        doc.campos_faltando.append("valor_servico")

    bloco = achar_elemento(raiz, TAGS_TOMADOR)
    if bloco is not None:
        doc.tomador_cnpj = normalizar_cnpj(achar_texto(bloco, TAGS_CNPJ))
    if not doc.tomador_cnpj:
        doc.campos_faltando.append("tomador_cnpj")

    return doc


# ---------------------------------------------------------------------------
# Cliente HTTP com backoff (spec §3.4)
# ---------------------------------------------------------------------------


def espera_backoff(tentativa: int, retry_after: str | None) -> float:
    """Exponencial com jitter total. `Retry-After` do servidor tem prioridade."""
    if retry_after:
        try:
            return min(float(retry_after), BACKOFF_MAX_S)
        except ValueError:
            pass
    teto = min(BACKOFF_BASE_S * (BACKOFF_FATOR**tentativa), BACKOFF_MAX_S)
    return random.uniform(0.0, teto)


def buscar_nsu(
    cliente: httpx.Client, nsu: int, cnpj_consulta: str | None, log: Any
) -> httpx.Response:
    params = {}
    if cnpj_consulta:
        # O manual v1.0 cita "um novo parâmetro" para consultar CNPJ distinto do
        # certificado, mas não dá o nome. HIPÓTESE — confirmar no Swagger.
        params["cnpj"] = cnpj_consulta

    ultimo: httpx.Response | None = None
    for tentativa in range(MAX_TENTATIVAS):
        resp = cliente.get(ROTA_DFE.format(nsu=nsu), params=params)
        if resp.status_code not in STATUS_RETENTAVEIS:
            return resp
        ultimo = resp
        pausa = espera_backoff(tentativa, resp.headers.get("Retry-After"))
        log(
            f"  NSU {nsu}: HTTP {resp.status_code}, nova tentativa em {pausa:.1f}s "
            f"({tentativa + 1}/{MAX_TENTATIVAS})"
        )
        time.sleep(pausa)

    assert ultimo is not None
    raise FalhaPermanente(
        f"NSU {nsu}: {MAX_TENTATIVAS} tentativas esgotadas, último status "
        f"HTTP {ultimo.status_code}."
    )


def percorrer_fila(
    cliente: httpx.Client,
    nsu_inicial: int,
    cnpj_consulta: str | None,
    dir_contrato: Path,
    log: Any,
    dump_contrato: bool,
    limite_lotes: int | None,
) -> Iterator[Documento]:
    """Percorre GET /DFe/{NSU} a partir de nsu_inicial até a fila esvaziar."""
    nsu = nsu_inicial
    lotes = 0

    while True:
        resp = buscar_nsu(cliente, nsu, cnpj_consulta, log)

        if resp.status_code == 204 or not resp.content:
            log(f"  NSU {nsu}: fila vazia (HTTP {resp.status_code}). Fim.")
            return
        if resp.status_code == 404:
            log(f"  NSU {nsu}: HTTP 404 — tratando como fim da fila.")
            return
        if resp.status_code >= 400:
            raise FalhaPermanente(
                f"NSU {nsu}: HTTP {resp.status_code}. Corpo: {resp.text[:500]}"
            )

        destino = dir_contrato / f"dfe_nsu{nsu:012d}.json"
        destino.write_bytes(resp.content)

        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise ContratoDesconhecido(
                f"NSU {nsu}: resposta não é JSON ({exc}). Salva em {destino}."
            ) from None

        if dump_contrato:
            log("\n=== CONTRATO CRU (primeira resposta não vazia) ===")
            log(f"HTTP {resp.status_code}")
            for k, v in resp.headers.items():
                log(f"  {k}: {v}")
            log(f"chaves de topo: {sorted(payload.keys())}")
            log(json.dumps(payload, indent=2, ensure_ascii=False)[:8000])
            log(f"\nresposta completa em {destino}")
            return

        k_lote = exigir_chave(payload, CANDIDATOS_LOTE, "lote de documentos", destino)
        lote = payload[k_lote] or []
        if not lote:
            log(f"  NSU {nsu}: lote vazio. Fim.")
            return

        maior_nsu = nsu
        for item in lote:
            k_nsu = exigir_chave(item, CANDIDATOS_NSU_DOC, "NSU do documento", destino)
            k_cont = exigir_chave(item, CANDIDATOS_CONTEUDO, "conteúdo XML", destino)
            k_tipo = primeiro_presente(item, CANDIDATOS_TIPO)

            nsu_doc = int(item[k_nsu])
            maior_nsu = max(maior_nsu, nsu_doc)
            yield interpretar_xml(
                Documento(
                    nsu=nsu_doc,
                    xml=decodificar_conteudo(item[k_cont]),
                    tipo_bruto=str(item[k_tipo]) if k_tipo else None,
                )
            )

        lotes += 1
        log(f"  NSU {nsu}: {len(lote)} documento(s), maior NSU {maior_nsu}")

        k_max = primeiro_presente(payload, CANDIDATOS_MAX_NSU)
        if k_max and int(payload[k_max]) <= maior_nsu:
            log(f"  alcançado {k_max}={payload[k_max]}. Fim.")
            return
        if limite_lotes and lotes >= limite_lotes:
            log(f"  limite de {limite_lotes} lote(s) atingido (--limite-lotes).")
            return

        nsu = maior_nsu + 1
        time.sleep(INTERVALO_ENTRE_LOTES_S)


# ---------------------------------------------------------------------------
# Resumo (spec §12)
# ---------------------------------------------------------------------------


def moeda(v: Decimal) -> str:
    q = v.quantize(Decimal("0.01"))
    inteiro, _, centavos = f"{q:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return ("-" if negativo else "") + ".".join(grupos) + "," + centavos


def imprimir_resumo(
    docs: list[Documento], cnpj_alvo: str, competencia_alvo: str, escrever: Any
) -> Decimal:
    notas = [d for d in docs if not d.eh_evento]
    eventos = [d for d in docs if d.eh_evento]

    escrever("")
    escrever("=" * 62)
    escrever("RESUMO DA CAPTURA")
    escrever("=" * 62)
    escrever(f"Documentos recebidos ........ {len(docs)}")
    escrever(f"  NFS-e ..................... {len(notas)}")
    escrever(f"  Eventos ................... {len(eventos)}")

    por_comp: Counter[str] = Counter(d.competencia or "(sem competência)" for d in notas)
    escrever("")
    escrever("Distribuição por competência:")
    for comp, qtd in sorted(por_comp.items()):
        escrever(f"  {comp} .... {qtd:5d}")

    alvo = [
        d
        for d in notas
        if d.competencia == competencia_alvo
        and d.tomador_cnpj == cnpj_alvo
        and d.valor_servico is not None
    ]
    total = sum((d.valor_servico or Decimal(0) for d in alvo), Decimal(0))

    escrever("")
    escrever(f"Notas de {competencia_alvo} com {cnpj_alvo} como TOMADOR:")
    escrever(f"  Quantidade ................ {len(alvo)}")
    escrever(f"  Somatório valor_servico ... R$ {moeda(total)}")

    incompletos = [d for d in notas if d.campos_faltando]
    if incompletos:
        escrever("")
        escrever(f"!! {len(incompletos)} nota(s) com campos não extraídos.")
        motivos: Counter[str] = Counter()
        for d in incompletos:
            motivos.update(d.campos_faltando)
        for motivo, qtd in motivos.most_common():
            escrever(f"   {motivo}: {qtd}")
        escrever("   O total acima está INCOMPLETO. Ajuste o bloco HIPÓTESES.")

    escrever("=" * 62)
    return total


def inspecionar(doc: Documento, escrever: Any) -> None:
    """Imprime a árvore de tags do XML — fecha o layout sem adivinhação."""
    escrever(f"\n=== ÁRVORE DO XML (NSU {doc.nsu}) ===")
    try:
        raiz = ET.fromstring(doc.xml)
    except ET.ParseError as exc:
        escrever(f"XML inválido: {exc}")
        return

    def caminhar(el: ET.Element, nivel: int) -> None:
        texto = (el.text or "").strip()
        resumo = f" = {texto[:60]}" if texto else ""
        attrs = f" {dict(el.attrib)}" if el.attrib else ""
        escrever("  " * nivel + localname(el.tag) + attrs + resumo)
        for filho in el:
            caminhar(filho, nivel + 1)

    caminhar(raiz, 0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--ambiente", choices=("restrita", "producao"), required=True)
    p.add_argument("--pfx", type=Path, help="caminho do .pfx (ou env NFSE_PFX_PATH)")
    p.add_argument("--nsu-inicial", type=int, default=0)
    p.add_argument(
        "--cnpj-consulta", help="consultar CNPJ distinto do certificado (mesma raiz)"
    )
    p.add_argument("--competencia", default="2026-08", help="competência do resumo (AAAA-MM)")
    p.add_argument("--saida", type=Path, default=Path("poc/out"))
    p.add_argument("--limite-lotes", type=int, help="para cedo; útil em testes")
    p.add_argument(
        "--dump-contrato", action="store_true",
        help="salva e imprime a primeira resposta crua, e para",
    )
    p.add_argument(
        "--inspecionar-xml", action="store_true",
        help="imprime a árvore de tags do primeiro XML, e para",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    log = lambda msg: print(msg, flush=True)  # noqa: E731

    caminho_pfx = args.pfx or (
        Path(os.environ["NFSE_PFX_PATH"]) if "NFSE_PFX_PATH" in os.environ else None
    )
    if caminho_pfx is None:
        log("ERRO: informe --pfx ou a variável NFSE_PFX_PATH.")
        return 2
    if not caminho_pfx.is_file():
        log(f"ERRO: {caminho_pfx} não existe.")
        return 2

    senha_txt = os.environ.get("NFSE_PFX_PASSWORD")
    if senha_txt is None:
        senha_txt = getpass.getpass("Senha do certificado: ")
    senha = senha_txt.encode()
    del senha_txt

    dir_xml = args.saida / "xml"
    dir_contrato = args.saida / "contrato"
    dir_xml.mkdir(parents=True, exist_ok=True)
    dir_contrato.mkdir(parents=True, exist_ok=True)

    pem: Path | None = None
    try:
        ctx, meta, pem = carregar_certificado(caminho_pfx.read_bytes(), senha)
        log(f"Certificado: {meta.titular_nome}")
        log(f"  CNPJ {meta.titular_cnpj} (raiz {meta.cnpj_raiz})")
        log(f"  válido de {meta.valido_de} até {meta.valido_ate}")

        cnpj_alvo = normalizar_cnpj(args.cnpj_consulta) or meta.titular_cnpj
        if args.cnpj_consulta and normalizar_cnpj(args.cnpj_consulta)[:8] != meta.cnpj_raiz:
            log("ERRO: o CNPJ raiz do certificado não bate com --cnpj-consulta. "
                "O ADN valida a raiz e vai recusar (Manual ADN v1.0, §1.1).")
            return 2

        base = BASE_URLS[args.ambiente]
        log(f"\nAmbiente: {args.ambiente} ({base})")
        log(f"Varrendo a fila a partir do NSU {args.nsu_inicial}...\n")

        docs: list[Documento] = []
        with httpx.Client(base_url=base, verify=ctx, timeout=60.0,
                          headers={"Accept": "application/json"}) as cliente:
            for doc in percorrer_fila(
                cliente, args.nsu_inicial, args.cnpj_consulta, dir_contrato,
                log, args.dump_contrato, args.limite_lotes,
            ):
                (dir_xml / doc.nome_arquivo).write_bytes(doc.xml)
                docs.append(doc)
                if args.inspecionar_xml:
                    inspecionar(doc, log)
                    return 0

        if args.dump_contrato:
            log("\nContrato salvo. Atualize o bloco HIPÓTESES e rode de novo sem --dump-contrato.")
            return 0

        if not docs:
            log("Nenhum documento retornado.")
            return 1

        log(f"\n{len(docs)} XML(s) gravado(s) em {dir_xml}")
        imprimir_resumo(docs, cnpj_alvo, args.competencia, log)
        return 0

    except (ContratoDesconhecido, FalhaPermanente) as exc:
        log(f"\nPAREI: {exc}")
        return 1
    except httpx.HTTPError as exc:
        log(f"\nFalha de rede/TLS: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if pem is not None:
            pem.unlink(missing_ok=True)
        del senha


if __name__ == "__main__":
    sys.exit(main())

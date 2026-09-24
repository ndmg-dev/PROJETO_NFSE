"""Instalação local no Windows (sem Docker, sem Redis, sem Celery).

O conjunto mínimo de dependências (requirements-local.txt) só funciona se a API
não importar mais nada. Estes testes impedem que isso se desatualize em silêncio:
um import novo sem o pacote no lock só quebraria na máquina do usuário.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

from app.setup import verificacoes

RAIZ = Path(__file__).resolve().parents[1]

# Módulo importado -> pacote no requirements-local.txt
PACOTE_DO_MODULO = {
    "bcrypt": "bcrypt",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "openpyxl": "openpyxl",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "sqlalchemy": "sqlalchemy",
}
# Pacotes que a API usa sem importar diretamente (dialeto, migrations, servidor, EmailStr).
PACOTES_INDIRETOS = {"alembic", "psycopg", "uvicorn", "email-validator"}


def _nomes(caminho: Path) -> set[str]:
    achados: set[str] = set()
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#")[0].strip()
        if not linha or linha.startswith(("-", "--")):
            continue
        achados.add(re.split(r"[=<>\[ ;]", linha, maxsplit=1)[0].lower().replace("_", "-"))
    return achados


# Imports sob demanda (dentro de função) permitidos: só rodam se o recurso opcional
# estiver configurado. Qualquer outro import preguiçoso de terceiros exige decisão.
OPCIONAIS_SOB_DEMANDA = {"redis"}


def _imports_de_terceiros_da_api() -> tuple[set[str], set[str]]:
    """(imports de topo de módulo, imports dentro de função), só de terceiros."""
    stdlib = sys.stdlib_module_names
    de_topo: set[str] = set()
    sob_demanda: set[str] = set()
    for arquivo in (RAIZ / "app").rglob("*.py"):
        if "workers" in arquivo.parts:  # celery e redis são só dos workers
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        dentro_de_funcao = {
            id(filho)
            for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)
            for filho in ast.walk(no)
        }
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                nomes = {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                nomes = {no.module.split(".")[0]}
            else:
                continue
            alvo = sob_demanda if id(no) in dentro_de_funcao else de_topo
            alvo.update(n for n in nomes if n not in stdlib and n not in {"app", "__future__"})
    return de_topo, sob_demanda


def test_a_api_so_importa_o_que_o_requirements_local_traz() -> None:
    usados, sob_demanda = _imports_de_terceiros_da_api()
    assert sob_demanda <= OPCIONAIS_SOB_DEMANDA, (
        f"import preguiçoso novo de terceiros: {sorted(sob_demanda - OPCIONAIS_SOB_DEMANDA)}. "
        "Se for opcional de verdade, acrescente a OPCIONAIS_SOB_DEMANDA."
    )
    desconhecidos = usados - set(PACOTE_DO_MODULO)
    assert not desconhecidos, (
        f"a API importa {sorted(desconhecidos)}, que não está no requirements-local.txt. "
        "Acrescente o pacote lá, regenere o .lock e atualize PACOTE_DO_MODULO."
    )
    declarados = _nomes(RAIZ / "requirements-local.txt")
    for modulo in usados:
        assert PACOTE_DO_MODULO[modulo] in declarados, modulo


def test_requirements_local_tem_os_pacotes_indiretos() -> None:
    assert _nomes(RAIZ / "requirements-local.txt") >= PACOTES_INDIRETOS


def test_o_que_e_de_worker_e_de_desenvolvimento_fica_fora() -> None:
    local = _nomes(RAIZ / "requirements-local.txt")
    for fora in ("celery", "redis", "pytest", "ruff", "mypy", "respx"):
        assert fora not in local, f"{fora} não deve ir para a instalação local"


def test_lock_tem_hash_em_todo_pacote_e_cobre_o_requirements() -> None:
    texto = (RAIZ / "requirements-local.lock").read_text(encoding="utf-8")
    pacotes = re.findall(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+)", texto, re.M)
    assert len(pacotes) >= 20
    blocos = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", texto.strip())
    sem_hash = [b.splitlines()[0] for b in blocos if "--hash=sha256:" not in b]
    assert not sem_hash, f"pacotes sem hash no lock: {sem_hash}"
    no_lock = {n.lower().replace("_", "-") for n, _ in pacotes}
    assert _nomes(RAIZ / "requirements-local.txt") <= no_lock


def test_api_importa_sem_redis_nem_celery() -> None:
    """Simula a instalação local: os dois pacotes bloqueados, a API tem de subir."""
    codigo = (
        "import sys; sys.modules['redis'] = None; sys.modules['celery'] = None; "
        "import app.api.main; print('importou')"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    assert "importou" in r.stdout


def test_sem_redis_configurado_nao_ha_verificacao_de_fila(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class SemRedis:
        redis_url = None

    monkeypatch.setattr(verificacoes, "obter_config", lambda: SemRedis())
    assert {v.id for v in verificacoes.verificar_sistema()} == {"banco", "esquema"}


def test_com_redis_configurado_ainda_confere_a_fila() -> None:
    assert "redis" in {v.id for v in verificacoes.verificar_sistema()}


# ==================================================== criação do banco local ===


def _url_admin_com(banco: str) -> str:
    import os

    from sqlalchemy.engine import make_url

    return make_url(os.environ["ADMIN_DATABASE_URL"]).set(database=banco).render_as_string(
        hide_password=False
    )


def test_garantir_banco_cria_e_e_idempotente(engine_admin) -> None:  # type: ignore[no-untyped-def]
    import uuid

    from sqlalchemy import text

    from app.local.preparar_banco import garantir_banco

    nome = f"nfse_teste_{uuid.uuid4().hex[:8]}"
    try:
        assert garantir_banco(_url_admin_com(nome)) is True, "deveria ter criado"
        assert garantir_banco(_url_admin_com(nome)) is False, "segunda vez não recria"
        with engine_admin.connect() as c:
            achado = c.execute(text("SELECT count(*) FROM pg_database WHERE datname = :n"),
                               {"n": nome}).scalar_one()
        assert achado == 1
    finally:
        with engine_admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{nome}"'))


def test_garantir_banco_recusa_nome_perigoso() -> None:
    import pytest

    from app.local.preparar_banco import garantir_banco

    for ruim in ('x"; DROP DATABASE nfse; --', "Maiusculas", "com espaco", "", "1abc"):
        with pytest.raises(ValueError):
            garantir_banco(_url_admin_com(ruim))

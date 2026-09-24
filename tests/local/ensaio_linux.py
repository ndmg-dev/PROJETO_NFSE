"""Ensaio da instalação local, no Linux: a MESMA sequência do instalador do Windows.

Não há Windows neste ambiente de desenvolvimento, mas há binários Linux do mesmo
PostgreSQL (Zonky 16.15.0). Este ensaio faz, num usuário sem privilégio e num
diretório novo, exatamente o que o instalador fará no Windows:

  baixar o PostgreSQL e conferir o SHA-256 publicado -> extrair -> initdb ->
  configurar (só 127.0.0.1) -> subir -> criar o banco -> aplicar as migrations ->
  subir a API SEM Redis -> percorrer o assistente e o painel -> reiniciar tudo e
  ver se os dados sobrevivem.

O que ele NÃO prova: nada do que é específico do Windows (postgres.exe, o Python
embutido e seu arquivo ._pth, o PowerShell, o cmd, o Visual C++). Prova que a
sequência, os parâmetros e o código da aplicação em modo local funcionam.

    make test-local
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import venv
import zipfile
from pathlib import Path

REPO = Path(os.environ.get("REPO", "/repo"))
BASE = Path(os.environ.get("HOME", "/tmp")) / "nfse-local"
PG_VERSAO = "16.15.0"
MAVEN = "https://repo1.maven.org/maven2/io/zonky/test/postgres"
PORTA_PG, PORTA_API = 54329, 8765
falhas = 0


def passo(texto: str) -> None:
    print(f"\n== {texto}", flush=True)


def conferir(nome: str, ok: bool, detalhe: str = "") -> None:
    global falhas
    print(
        f"  {'✓' if ok else '✗'} {nome}" + (f"  [{detalhe}]" if detalhe and not ok else ""),
        flush=True,
    )
    if not ok:
        falhas += 1


def baixar_verificado(url: str, sha256: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    with urllib.request.urlopen(url, timeout=120) as r, parcial.open("wb") as f:
        shutil.copyfileobj(r, f)
    real = hashlib.sha256(parcial.read_bytes()).hexdigest()
    if real != sha256.strip().lower():
        parcial.unlink()
        raise SystemExit(f"checksum não confere para {url}: esperado {sha256}, veio {real}")
    parcial.rename(destino)


def http(
    metodo: str,
    caminho: str,
    corpo: dict | None = None,
    token: str | None = None,
    seguir: bool = True,
) -> tuple[int, str, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORTA_API}{caminho}", method=metodo)
    if corpo is not None:
        req.data = json.dumps(corpo).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    class SemRedirecionar(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # type: ignore[no-untyped-def]
            return None

    abridor = (
        urllib.request.build_opener() if seguir else urllib.request.build_opener(SemRedirecionar)
    )
    try:
        with abridor.open(req, timeout=20) as r:
            return r.status, r.read().decode(errors="replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), dict(e.headers)


def rodar(
    cmd: list[str], env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=300)


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    for d in ("pgsql", "app", "dados", "logs", "cache"):
        (BASE / d).mkdir(parents=True)

    # ---------------------------------------------------------------- 1. baixar
    passo("1. PostgreSQL: baixar e conferir o SHA-256 publicado na Maven Central")
    jar = f"embedded-postgres-binaries-linux-amd64-{PG_VERSAO}.jar"
    url = f"{MAVEN}/embedded-postgres-binaries-linux-amd64/{PG_VERSAO}/{jar}"
    esperado = urllib.request.urlopen(url + ".sha256", timeout=60).read().decode().strip()
    baixar_verificado(url, esperado, BASE / "cache" / jar)
    conferir("download conferido contra o SHA-256 publicado", True)
    try:
        baixar_verificado(url, "0" * 64, BASE / "cache" / "de-mentira.jar")
        conferir("um SHA-256 errado é recusado", False)
    except SystemExit:
        conferir(
            "um SHA-256 errado é recusado (e o arquivo parcial some)",
            not (BASE / "cache" / "de-mentira.jar.parcial").exists(),
        )

    passo("2. Extrair: jar (zip) -> .txz -> pasta pgsql, só com a biblioteca padrão do Python")
    with zipfile.ZipFile(BASE / "cache" / jar) as z:
        txz = next(n for n in z.namelist() if n.endswith(".txz"))
        z.extract(txz, BASE / "cache")
    with tarfile.open(BASE / "cache" / txz, "r:xz") as t:
        t.extractall(BASE / "pgsql", filter="data")
    pg_bin = BASE / "pgsql" / "bin"
    for exe in ("postgres", "initdb", "pg_ctl"):
        conferir(f"{exe} presente", (pg_bin / exe).exists())

    # --------------------------------------------------------------- 3. Python
    passo("3. Dependências: as versões do requirements-local.lock (sem os hashes do Windows)")
    venv.EnvBuilder(with_pip=True).create(BASE / "python")
    py = BASE / "python" / "bin" / "python"
    fixas = [
        ln.split()[0]
        for ln in (REPO / "requirements-local.lock").read_text().splitlines()
        if ln and not ln.startswith((" ", "#", "-")) and "==" in ln.split()[0]
    ]
    (BASE / "cache" / "fixas.txt").write_text("\n".join(fixas) + "\n")
    r = rodar(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "-q",
            "--no-deps",
            "-r",
            str(BASE / "cache" / "fixas.txt"),
        ],
        os.environ.copy(),
    )
    conferir(
        f"{len(fixas)} pacotes instalados nas versões travadas", r.returncode == 0, r.stderr[-300:]
    )
    for n in ("app", "alembic"):
        shutil.copytree(REPO / n, BASE / "app" / n, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(REPO / "alembic.ini", BASE / "app" / "alembic.ini")
    lista = rodar(
        [str(py), "-m", "pip", "list", "--format=freeze"], os.environ.copy()
    ).stdout.lower()
    conferir(
        "Celery e Redis NÃO estão instalados (a API local não os usa)",
        "celery" not in lista and "redis" not in lista,
    )

    # ------------------------------------------------------------------ 4. initdb
    passo("4. initdb: cluster novo, autenticação por senha, só 127.0.0.1")
    senha_pg, senha_app, jwt = (
        secrets.token_hex(24),
        secrets.token_hex(24),
        secrets.token_urlsafe(32),
    )
    import base64

    jwt = base64.b64encode(secrets.token_bytes(32)).decode()
    pwfile = BASE / "cache" / "pg.pw"
    pwfile.write_text(senha_pg)
    pwfile.chmod(0o600)
    dados = BASE / "dados" / "pg"
    r = rodar(
        [
            str(pg_bin / "initdb"),
            "-D",
            str(dados),
            "-U",
            "nfse",
            "-E",
            "UTF8",
            "--locale=C",
            "--auth=scram-sha-256",
            f"--pwfile={pwfile}",
        ],
        os.environ.copy(),
    )
    conferir("initdb terminou", r.returncode == 0, r.stderr[-400:] + r.stdout[-200:])
    pwfile.unlink()
    conferir("o arquivo temporário da senha foi apagado", not pwfile.exists())
    with (dados / "postgresql.conf").open("a") as f:
        f.write(
            f"\nlisten_addresses = '127.0.0.1'\nport = {PORTA_PG}\nmax_connections = 30\n"
            "shared_buffers = 64MB\nunix_socket_directories = ''\n"
        )

    def pg(acao: str) -> subprocess.CompletedProcess[str]:
        args = [str(pg_bin / "pg_ctl"), "-D", str(dados), "-w", "-t", "60", acao]
        if acao == "start":
            args[1:1] = ["-l", str(BASE / "logs" / "postgres.log")]
        if acao == "stop":
            args += ["-m", "fast"]
        return rodar(args, os.environ.copy())

    passo("5. Subir o PostgreSQL e criar o banco (sem createdb nem psql)")
    r = pg("start")
    conferir("pg_ctl start", r.returncode == 0, r.stderr[-300:] + r.stdout[-300:])
    admin = f"postgresql+psycopg://nfse:{senha_pg}@127.0.0.1:{PORTA_PG}/nfse"
    env = {
        **os.environ,
        "DATABASE_URL": admin,
        "APP_DB_PASSWORD": senha_app,
        "PYTHONPATH": str(BASE / "app"),
    }
    env.pop("REDIS_URL", None)
    r = rodar([str(py), "-m", "app.local.preparar_banco"], env, BASE / "app")
    conferir(
        "banco criado pelo driver Python",
        r.returncode == 0 and "criado" in r.stdout,
        r.stderr[-300:],
    )
    r = rodar([str(py), "-m", "app.local.preparar_banco"], env, BASE / "app")
    conferir("segunda execução é idempotente", "já existia" in r.stdout)

    passo("6. Migrations")
    r = rodar([str(py), "-m", "alembic", "upgrade", "head"], env, BASE / "app")
    conferir("alembic upgrade head", r.returncode == 0, r.stderr[-500:])

    # -------------------------------------------------------------------- 7. API
    passo("7. API em modo local: só 127.0.0.1 e SEM Redis")
    app_url = f"postgresql+psycopg://nfse_app:{senha_app}@127.0.0.1:{PORTA_PG}/nfse"
    env_api = {
        **os.environ,
        "DATABASE_URL": app_url,
        "JWT_SECRET": jwt,
        "PYTHONPATH": str(BASE / "app"),
    }
    env_api.pop("REDIS_URL", None)
    logapi = (BASE / "logs" / "api.log").open("w")

    def subir_api() -> subprocess.Popen[bytes]:
        p = subprocess.Popen(
            [
                str(py),
                "-m",
                "uvicorn",
                "app.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORTA_API),
            ],
            env=env_api,
            cwd=BASE / "app",
            stdout=logapi,
            stderr=logapi,
        )
        for _ in range(60):
            try:
                if http("GET", "/health")[0] == 200:
                    return p
            except Exception:
                time.sleep(0.5)
        p.kill()
        raise SystemExit("a API não subiu; veja " + str(BASE / "logs" / "api.log"))

    api = subir_api()
    conferir("/health responde", http("GET", "/health")[0] == 200)
    corpo = json.loads(http("GET", "/setup/status")[1])
    ids = [v["id"] for v in corpo["verificacoes"]]
    conferir("status: ainda não configurado", corpo["configurado"] is False)
    conferir(
        "verificações: banco e estrutura, e NENHUMA de Redis", ids == ["banco", "esquema"], str(ids)
    )
    conferir("todas as verificações ok", all(v["ok"] for v in corpo["verificacoes"]))
    st, _, cab = http("GET", "/", seguir=False)
    conferir("a raiz manda para /setup", st == 307 and cab.get("location") == "/setup")

    passo("8. O assistente e o painel")
    codigo = rodar([str(py), "-m", "app.setup.codigo"], env_api, BASE / "app").stdout.strip()
    conferir(
        "o código de configuração sai do comando", len(codigo) == 9 and codigo[4] == "-", codigo
    )
    ok = {"escritorio": "Escritório Local", "email": "Ana@Local.com", "senha": "uma-senha-longa-1"}
    conferir(
        "código errado -> 403", http("POST", "/setup", {**ok, "codigo": "AAAA-AAAA"})[0] == 403
    )
    conferir("código certo -> 201", http("POST", "/setup", {**ok, "codigo": codigo})[0] == 201)
    conferir("segundo setup -> 409", http("POST", "/setup", {**ok, "codigo": codigo})[0] == 409)
    st, corpo, _ = http("POST", "/auth/login", {"email": "ana@local.com", "senha": ok["senha"]})
    conferir("login", st == 200)
    token = json.loads(corpo)["access_token"]
    st, corpo, _ = http(
        "POST",
        "/empresas",
        {"cnpj": "07.199.546/0001-62", "razao_social": "AB ENGENHARIA LTDA"},
        token,
    )
    conferir("cadastrar empresa", st == 201, corpo[:200])
    st, corpo, _ = http("GET", "/empresas", token=token)
    conferir("listar empresas", st == 200 and json.loads(corpo)[0]["cnpj_raiz"] == "07199546")
    conferir(
        "relatório de retenções responde (XLSX)",
        http("GET", f"/empresas/{json.loads(corpo)[0]['id']}/retencoes", token=token)[0] == 200,
    )
    conferir("página /instalar", http("GET", "/instalar")[0] == 200)
    conferir("o painel em /", http("GET", "/")[0] == 200)

    passo("9. A API não ficou exposta na rede (só em 127.0.0.1)")
    conferir("/health por 127.0.0.1", http("GET", "/health")[0] == 200)
    saida = rodar(
        ["sh", "-c", "cat /proc/net/tcp | awk 'NR>1 && $4==\"0A\" {print $2}'"], os.environ.copy()
    ).stdout.split()
    porta_hex = f":{PORTA_API:04X}"
    escutando = [e for e in saida if e.endswith(porta_hex) or e.endswith(f":{PORTA_PG:04X}")]
    conferir(
        "API e PostgreSQL escutam SÓ em 127.0.0.1 (0100007F)",
        bool(escutando) and all(e.startswith("0100007F") for e in escutando),
        str(escutando),
    )

    # ------------------------------------------------------------- 10. reiniciar
    passo("10. Desligar tudo e ligar de novo: os dados sobrevivem?")
    api.terminate()
    api.wait(timeout=20)
    conferir("pg_ctl stop -m fast", pg("stop").returncode == 0)
    conferir("pg_ctl start de novo", pg("start").returncode == 0)
    api = subir_api()
    st, corpo, _ = http("POST", "/auth/login", {"email": "ana@local.com", "senha": ok["senha"]})
    conferir("o usuário criado no assistente continua entrando", st == 200)
    st, corpo, _ = http("GET", "/empresas", token=json.loads(corpo)["access_token"])
    conferir("a empresa cadastrada continua lá", st == 200 and len(json.loads(corpo)) == 1)
    conferir(
        "/setup/status agora diz configurado e não expõe infraestrutura",
        json.loads(http("GET", "/setup/status")[1]) == {"configurado": True, "verificacoes": []},
    )

    passo("11. Nenhuma senha nos logs")
    api.terminate()
    api.wait(timeout=20)
    pg("stop")
    logs = "".join(p.read_text(errors="ignore") for p in (BASE / "logs").glob("*.log"))
    for nome, valor in (
        ("senha do postgres", senha_pg),
        ("senha do papel da app", senha_app),
        ("JWT_SECRET", jwt),
        ("senha do administrador", ok["senha"]),
    ):
        conferir(f"{nome} não aparece nos logs", valor not in logs)

    print("\n" + (f"{falhas} FALHA(S)" if falhas else "ensaio concluído: tudo certo"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

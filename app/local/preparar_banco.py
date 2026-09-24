"""Cria o banco de dados da instalação local, se ainda não existir.

O pacote de PostgreSQL da instalação local (Windows) traz só postgres, initdb e
pg_ctl: não tem createdb nem psql. O initdb cria o banco `postgres`, e o sistema
usa outro (`nfse`), então alguém precisa criá-lo. Este módulo faz isso pelo
próprio driver Python, e é idempotente: rodar de novo não faz nada.

    DATABASE_URL=postgresql+psycopg://nfse:SENHA@127.0.0.1:54329/nfse \\
        python -m app.local.preparar_banco
"""

from __future__ import annotations

import os
import re
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

# O nome entra na DDL (CREATE DATABASE não aceita parâmetro), então só passa o
# que é identificador simples.
_NOME_VALIDO = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def garantir_banco(url_admin: str, *, espera_s: float = 30.0) -> bool:
    """Devolve True se criou, False se já existia. Espera o servidor aceitar conexão."""
    url = make_url(url_admin)
    nome = url.database
    if not nome or not _NOME_VALIDO.match(nome):
        raise ValueError(f"nome de banco inválido: {nome!r}")

    motor = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    limite = time.monotonic() + espera_s
    try:
        while True:
            try:
                with motor.connect() as c:
                    existe = c.execute(
                        text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nome}
                    ).first()
                    if existe:
                        return False
                    # template0 + UTF8: o padrão herdaria o encoding do sistema, que no
                    # Windows não é UTF-8.
                    c.execute(
                        text(f'CREATE DATABASE "{nome}" ENCODING \'UTF8\' TEMPLATE template0')
                    )
                    return True
            except OperationalError:
                if time.monotonic() > limite:
                    raise
                time.sleep(0.5)
    finally:
        motor.dispose()


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL não definida", file=sys.stderr)
        return 2
    criou = garantir_banco(url)
    print("banco criado" if criou else "banco já existia")
    return 0


if __name__ == "__main__":
    sys.exit(main())

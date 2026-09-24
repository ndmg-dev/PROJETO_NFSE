"""Confere, na rede, que cada pino de app/instalador/pins.json ainda baixa o mesmo arquivo.

Rodar ao trocar uma versão e de vez em quando: se uma fonte mudar o arquivo sem mudar a
URL, o instalador passaria a recusar o download (o que é o comportamento certo, mas o
usuário só descobriria na instalação).

    python -m app.instalador.verificar_pins
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

PINS = Path(__file__).with_name("pins.json")


def sha256_da_url(url: str) -> str:
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=180) as r:  # noqa: S310 - https fixo do pins.json
        for bloco in iter(lambda: r.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def main() -> int:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    falhas = 0
    for nome, pino in pins.items():
        if not isinstance(pino, dict) or "url" not in pino:
            continue
        real = sha256_da_url(pino["url"])
        ok = real == pino["sha256"]
        falhas += 0 if ok else 1
        print(f"{'ok ' if ok else 'ERRO'} {nome} {pino.get('versao', '')}"
              + ("" if ok else f"\n     esperado {pino['sha256']}\n     veio     {real}"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

"""Código de configuração inicial.

Antes do primeiro acesso, /setup cria o administrador sem exigir login — é
inevitável, ainda não há ninguém. Isso é o clássico "quem chegar primeiro toma o
sistema": qualquer pessoa que alcance o servidor na rede antes do dono poderia
reivindicá-lo. O código fecha essa porta: só quem tem acesso ao servidor (que
lê o código no log da subida, ou o recebe na URL que o instalador abre) consegue
completar o setup.

O código é DERIVADO do JWT_SECRET por HMAC, não sorteado e guardado: é o mesmo em
todos os processos e sobrevive a reinício sem precisar de tabela nem arquivo, e
quem já tem o segredo do servidor já poderia forjar qualquer coisa. Depois que o
setup termina, o endpoint se tranca e o código deixa de servir para qualquer
coisa.

    python -m app.setup.codigo     # imprime o código deste servidor
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

_CONTEXTO = b"nfse-setup-v1"
_FORA_DO_ALFABETO = re.compile(r"[^A-Z2-7]")


def codigo_de_configuracao(segredo: str) -> str:
    """`K7QH-2MXP`: 8 caracteres base32 (40 bits), sem 0/1/8/9 para não confundir."""
    mac = hmac.new(segredo.encode(), _CONTEXTO, hashlib.sha256).digest()
    texto = base64.b32encode(mac).decode()[:8]
    return f"{texto[:4]}-{texto[4:]}"


def _normalizar(codigo: str) -> str:
    return _FORA_DO_ALFABETO.sub("", codigo.upper())


def codigo_confere(informado: str, segredo: str) -> bool:
    """Tolerante a caixa, hífen e espaço; comparação em tempo constante."""
    esperado = _normalizar(codigo_de_configuracao(segredo))
    return hmac.compare_digest(_normalizar(informado), esperado)


if __name__ == "__main__":
    from app.core.config import obter_config

    print(codigo_de_configuracao(obter_config().jwt_secret.get_secret_value()))

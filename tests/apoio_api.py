"""Constantes e helper compartilhados pelos testes de API."""

from __future__ import annotations

from fastapi.testclient import TestClient

CNPJ = "07199546000162"
SENHA_USUARIO = "senha-de-teste-123"


def entrar(cliente: TestClient, email: str) -> dict[str, str]:
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA_USUARIO})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

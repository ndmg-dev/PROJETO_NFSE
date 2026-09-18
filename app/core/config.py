"""Configuração. Segredo só entra por ambiente — nunca por default no código."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    # SecretStr para não vazar em repr/log/traceback — a §8 proíbe.
    cofre_master_key: SecretStr = Field(alias="COFRE_MASTER_KEY")
    jwt_secret: SecretStr = Field(alias="JWT_SECRET")

    ambiente_adn: Literal["restrita", "producao"] = Field(
        default="restrita", alias="AMBIENTE_ADN"
    )
    access_token_minutos: int = 15
    refresh_token_dias: int = 7

    @field_validator("cofre_master_key", "jwt_secret")
    @classmethod
    def _exigir_segredo_forte(cls, v: SecretStr) -> SecretStr:
        import base64
        import binascii

        bruto = v.get_secret_value()
        if not bruto:
            raise ValueError("segredo vazio — gere um com os.urandom(32)")
        try:
            if len(base64.b64decode(bruto, validate=True)) < 32:
                raise ValueError("segredo com menos de 32 bytes")
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"segredo inválido: {exc}") from None
        return v


@lru_cache
def obter_config() -> Config:
    return Config()  # type: ignore[call-arg]

"""Configuração por variáveis de ambiente (prefixo LUPA_), validada no boot."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AVISO = (
    "Programa de demonstração, feito para portfólio. Não é aconselhamento jurídico e não "
    "deve ser usado para decisões reais. Na dúvida, consulte um advogado ou a Defensoria Pública."
)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LUPA_", env_file=".env", extra="ignore")

    groq_api_key: SecretStr | None = None
    groq_modelo: str = "openai/gpt-oss-120b"
    groq_url: str = "https://api.groq.com/openai/v1"

    gemini_api_key: SecretStr | None = None
    gemini_modelo: str = "gemini-2.5-flash"
    gemini_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    database_url: str | None = "sqlite:///./lupa.db"

    cors_origens: list[str] = [
        "https://sirdann-sys.github.io",
        "https://sunnar.com.br",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    max_caracteres: int = 40_000
    max_clausulas: int = 80
    max_pdf_bytes: int = 5_000_000
    max_paginas: int = 20

    limite_por_ip: int = 10
    janela_ip_segundos: int = 600
    limite_diario: int = 300

    cache_ttl_segundos: int = 86_400
    cache_max_itens: int = 500

    @field_validator("database_url")
    @classmethod
    def _driver_postgres(cls, url: str | None) -> str | None:
        """Neon e Render entregam `postgres(ql)://`; o SQLAlchemy precisa saber o driver."""
        if url and url.startswith(("postgres://", "postgresql://")):
            return "postgresql+psycopg://" + url.split("://", 1)[1]
        return url or None


@lru_cache
def obter_config() -> Config:
    return Config()

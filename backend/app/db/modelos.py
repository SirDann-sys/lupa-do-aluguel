"""Tabelas. Só métricas de uso: nenhuma coluna guarda texto do contrato."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _agora() -> datetime:
    return datetime.now(UTC)


class Execucao(Base):
    __tablename__ = "execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora, index=True)
    origem: Mapped[str] = mapped_column(String(10))  # texto | pdf
    status: Mapped[str] = mapped_column(String(30), index=True)  # ok | <codigo de erro>
    provedor: Mapped[str | None] = mapped_column(String(30))
    modelo: Mapped[str | None] = mapped_column(String(80))
    em_cache: Mapped[bool] = mapped_column(default=False)
    usou_reserva: Mapped[bool] = mapped_column(default=False)
    clausulas: Mapped[int] = mapped_column(Integer, default=0)
    regras_violadas: Mapped[list[int]] = mapped_column(JSON, default=list)
    fatos_descartados: Mapped[int] = mapped_column(Integer, default=0)
    latencia_ms: Mapped[int] = mapped_column(Integer)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0)

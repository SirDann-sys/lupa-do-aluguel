"""Acesso ao banco: grava execuções e calcula as estatísticas públicas."""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.modelos import Execucao

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NovaExecucao:
    origem: str
    status: str
    latencia_ms: int
    provedor: str | None = None
    modelo: str | None = None
    em_cache: bool = False
    usou_reserva: bool = False
    clausulas: int = 0
    regras_violadas: tuple[int, ...] = ()
    fatos_descartados: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0


class Repositorio(Protocol):
    def registrar(self, execucao: NovaExecucao) -> None: ...
    def estatisticas(self, dias: int) -> dict[str, Any]: ...


def _percentil(valores: list[int], p: float) -> int | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    posicao = min(len(ordenados) - 1, round(p * (len(ordenados) - 1)))
    return ordenados[posicao]


class RepositorioSQL:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def de_url(cls, url: str) -> "RepositorioSQL":
        return cls(create_engine(url, pool_pre_ping=True))

    def registrar(self, execucao: NovaExecucao) -> None:
        """Grava a métrica. Falha de banco nunca derruba a análise do usuário."""
        dados = {**execucao.__dict__, "regras_violadas": list(execucao.regras_violadas)}
        try:
            with Session(self.engine) as sessao, sessao.begin():
                sessao.add(Execucao(**dados))
        except SQLAlchemyError:
            log.exception("falha_ao_registrar_execucao")

    def estatisticas(self, dias: int) -> dict[str, Any]:
        desde = datetime.now(UTC) - timedelta(days=dias)
        with Session(self.engine) as sessao:
            por_status = dict(
                sessao.execute(
                    select(Execucao.status, func.count())
                    .where(Execucao.criado_em >= desde)
                    .group_by(Execucao.status)
                ).all()
            )
            por_provedor = dict(
                sessao.execute(
                    select(Execucao.provedor, func.count())
                    .where(Execucao.criado_em >= desde, Execucao.status == "ok")
                    .group_by(Execucao.provedor)
                ).all()
            )
            sucesso = sessao.execute(
                select(
                    Execucao.latencia_ms,
                    Execucao.regras_violadas,
                    Execucao.em_cache,
                    Execucao.usou_reserva,
                ).where(Execucao.criado_em >= desde, Execucao.status == "ok")
            ).all()

        latencias = [linha.latencia_ms for linha in sucesso if not linha.em_cache]
        regras = Counter(r for linha in sucesso for r in linha.regras_violadas)
        total_ok = len(sucesso)
        return {
            "periodo_dias": dias,
            "analises": total_ok,
            "erros": sum(n for status, n in por_status.items() if status != "ok"),
            "por_status": por_status,
            "por_provedor": {str(k): v for k, v in por_provedor.items()},
            "taxa_reserva": round(sum(1 for linha in sucesso if linha.usou_reserva) / total_ok, 3)
            if total_ok
            else None,
            "latencia_ms": {"p50": _percentil(latencias, 0.5), "p95": _percentil(latencias, 0.95)},
            "regras_mais_violadas": {str(k): v for k, v in sorted(regras.items())},
        }


class RepositorioNulo:
    """Usado quando não há banco configurado: métricas desligadas."""

    def registrar(self, execucao: NovaExecucao) -> None:
        return None

    def estatisticas(self, dias: int) -> dict[str, Any]:
        return {
            "periodo_dias": dias,
            "analises": 0,
            "erros": 0,
            "por_status": {},
            "por_provedor": {},
            "taxa_reserva": None,
            "latencia_ms": {"p50": None, "p95": None},
            "regras_mais_violadas": {},
        }

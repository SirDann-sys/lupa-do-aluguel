"""Contrato comum de quem extrai fatos de cláusulas (LLM ou heurística)."""

from dataclasses import dataclass, field
from typing import Protocol

from app.dominio.modelos import FatosClausula


@dataclass(frozen=True)
class Extracao:
    fatos: list[FatosClausula]
    provedor: str
    modelo: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    falhas: list[str] = field(default_factory=list)


class ErroProvedor(Exception):
    """Falha de um provedor. `temporario` diz se vale tentar de novo (ou o próximo)."""

    def __init__(
        self, provedor: str, mensagem: str, *, temporario: bool, espera: float | None = None
    ) -> None:
        super().__init__(f"{provedor}: {mensagem}")
        self.provedor = provedor
        self.temporario = temporario
        self.espera = espera


class Extrator(Protocol):
    nome: str
    modelo: str

    async def extrair(self, clausulas: list[str]) -> Extracao: ...

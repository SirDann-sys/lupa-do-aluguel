import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.db.modelos import Base
from app.db.repositorio import NovaExecucao, RepositorioSQL
from app.dominio.modelos import Campo, Evidencia, FatosClausula, TipoGarantia
from app.llm.base import ErroProvedor, Extracao
from app.main import criar_app

CONTRATOS = Path(__file__).resolve().parents[2] / "avaliacao" / "contratos"

CONTRATO_CURTO = """\
CONTRATO DE LOCAÇÃO RESIDENCIAL

CLÁUSULA PRIMEIRA – DO ALUGUEL
O aluguel mensal é de R$ 2.000,00 (dois mil reais), pago até o dia 5.

CLÁUSULA SEGUNDA – DA GARANTIA
O LOCATÁRIO prestará caução em dinheiro equivalente a 5 (cinco) aluguéis.

CLÁUSULA TERCEIRA – DO REAJUSTE
O aluguel será reajustado anualmente pelo IPCA.
"""


def fatos(indice: int, **campos: object) -> FatosClausula:
    """Atalho: monta FatosClausula com uma evidência por campo afirmado."""
    evidencias = campos.pop("evidencias", [])
    return FatosClausula.model_validate({"indice": indice, "evidencias": evidencias, **campos})


def prova(campo: Campo, trecho: str) -> Evidencia:
    return Evidencia(campo=campo, trecho=trecho)


class ExtratorFixo:
    """Devolve fatos prontos, ou levanta os erros da fila, na ordem."""

    def __init__(
        self,
        nome: str = "fixo",
        respostas: list[list[FatosClausula] | ErroProvedor] | None = None,
        construir: Callable[[list[str]], list[FatosClausula]] | None = None,
    ) -> None:
        self.nome = nome
        self.modelo = f"{nome}-modelo"
        self._respostas = list(respostas or [])
        self._construir = construir
        self.chamadas = 0

    async def extrair(self, clausulas: list[str]) -> Extracao:
        self.chamadas += 1
        if self._construir:
            return Extracao(self._construir(clausulas), self.nome, self.modelo, 100, 50)
        resposta = self._respostas.pop(0)
        if isinstance(resposta, ErroProvedor):
            raise resposta
        return Extracao(resposta, self.nome, self.modelo, 100, 50)


def caucao_cinco_meses(clausulas: list[str]) -> list[FatosClausula]:
    """Extrator de teste para CONTRATO_CURTO: acha a caução de 5 meses na 2ª cláusula."""
    trecho = "caução em dinheiro equivalente a 5 (cinco) aluguéis"
    return [
        fatos(
            i,
            **(
                {
                    "garantias": [TipoGarantia.CAUCAO],
                    "caucao_meses": 5,
                    "evidencias": [prova(Campo.CAUCAO, trecho), prova(Campo.GARANTIAS, trecho)],
                }
                if trecho in c
                else {}
            ),
        )
        for i, c in enumerate(clausulas, start=1)
    ]


class RepositorioMemoria:
    def __init__(self) -> None:
        self.execucoes: list[NovaExecucao] = []

    def registrar(self, execucao: NovaExecucao) -> None:
        self.execucoes.append(execucao)

    def estatisticas(self, dias: int) -> dict[str, object]:
        return {"analises": len(self.execucoes)}


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        _env_file=None,
        groq_api_key=None,
        gemini_api_key=None,
        database_url=f"sqlite:///{tmp_path / 'teste.db'}",
        limite_por_ip=3,
    )


@pytest.fixture
def cliente(config: Config) -> Iterator[TestClient]:
    app = criar_app(config, extratores=[ExtratorFixo(construir=caucao_cinco_meses)])
    with TestClient(app) as c:
        yield c


@pytest.fixture
def url_banco(tmp_path: Path) -> str:
    """SQLite temporário; no CI, LUPA_TESTE_DATABASE_URL aponta para um PostgreSQL real."""
    url = os.environ.get("LUPA_TESTE_DATABASE_URL")
    return Config(_env_file=None, database_url=url).database_url or f"sqlite:///{tmp_path / 'r.db'}"


@pytest.fixture
def repositorio_sql(url_banco: str) -> Iterator[RepositorioSQL]:
    repositorio = RepositorioSQL.de_url(url_banco)
    Base.metadata.drop_all(repositorio.engine)
    Base.metadata.create_all(repositorio.engine)
    yield repositorio
    Base.metadata.drop_all(repositorio.engine)
    repositorio.engine.dispose()

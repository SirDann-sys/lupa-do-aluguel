from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config as ConfigAlembic
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.modelos import Base
from app.db.repositorio import NovaExecucao, RepositorioNulo, RepositorioSQL

BACKEND = Path(__file__).resolve().parents[1]


def test_registra_e_agrega(repositorio_sql: RepositorioSQL) -> None:
    for ms, regras, provedor in [
        (100, (1, 2), "groq"),
        (300, (1,), "groq"),
        (900, (), "heuristico"),
    ]:
        repositorio_sql.registrar(
            NovaExecucao(
                origem="texto",
                status="ok",
                latencia_ms=ms,
                provedor=provedor,
                regras_violadas=regras,
                usou_reserva=provedor == "heuristico",
            )
        )
    repositorio_sql.registrar(NovaExecucao(origem="pdf", status="entrada_invalida", latencia_ms=5))
    repositorio_sql.registrar(
        NovaExecucao(origem="texto", status="ok", latencia_ms=1, provedor="groq", em_cache=True)
    )

    dados = repositorio_sql.estatisticas(dias=30)

    assert dados["analises"] == 4
    assert dados["erros"] == 1
    assert dados["por_provedor"] == {"groq": 3, "heuristico": 1}
    assert dados["regras_mais_violadas"] == {"1": 2, "2": 1}
    assert dados["taxa_reserva"] == 0.25
    assert dados["latencia_ms"] == {"p50": 300, "p95": 900}  # o acerto de cache não entra


def test_banco_vazio(repositorio_sql: RepositorioSQL) -> None:
    dados = repositorio_sql.estatisticas(dias=1)
    assert dados["analises"] == 0
    assert dados["taxa_reserva"] is None
    assert dados["latencia_ms"] == {"p50": None, "p95": None}


def test_falha_do_banco_nao_derruba_a_analise(tmp_path: Path) -> None:
    sem_tabelas = RepositorioSQL.de_url(f"sqlite:///{tmp_path / 'vazio.db'}")
    sem_tabelas.registrar(NovaExecucao(origem="texto", status="ok", latencia_ms=1))


def test_repositorio_nulo() -> None:
    nulo = RepositorioNulo()
    nulo.registrar(NovaExecucao(origem="texto", status="ok", latencia_ms=1))
    assert nulo.estatisticas(7)["analises"] == 0


def test_migracoes_criam_exatamente_o_que_os_modelos_descrevem(url_banco: str) -> None:
    url = url_banco
    alembic = ConfigAlembic(str(BACKEND / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", url)

    command.upgrade(alembic, "head")

    engine = create_engine(url)
    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == []
    assert "execucoes" in inspect(engine).get_table_names()

    command.downgrade(alembic, "base")
    assert "execucoes" not in inspect(engine).get_table_names()
    engine.dispose()


def test_url_do_neon_ganha_o_driver() -> None:
    from app.config import Config

    config = Config(
        _env_file=None, database_url="postgresql://u:s@ep-x.neon.tech/db?sslmode=require"
    )
    assert config.database_url == "postgresql+psycopg://u:s@ep-x.neon.tech/db?sslmode=require"
    assert Config(_env_file=None, database_url="").database_url is None


def test_nenhuma_coluna_guarda_texto_de_contrato() -> None:
    colunas = {c.name for c in Base.metadata.tables["execucoes"].columns}
    proibidas = {"texto", "clausula", "clausulas_texto", "trecho", "conteudo", "contrato"}
    assert not colunas & proibidas

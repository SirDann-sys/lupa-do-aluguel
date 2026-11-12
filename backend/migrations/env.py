"""Ambiente do Alembic: usa a mesma URL e os mesmos modelos da aplicação."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import Config
from app.db.modelos import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

alvo = Base.metadata


def _url() -> str:
    url = context.config.get_main_option("sqlalchemy.url") or Config().database_url
    if not url:
        raise RuntimeError("Defina LUPA_DATABASE_URL para rodar as migrações.")
    return url


def rodar_offline() -> None:
    context.configure(url=_url(), target_metadata=alvo, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def rodar_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conexao:
        context.configure(connection=conexao, target_metadata=alvo, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    rodar_offline()
else:
    rodar_online()

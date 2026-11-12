"""Fábrica da aplicação FastAPI.

`criar_app` aceita as dependências prontas (cadeia de extratores, repositório),
o que permite aos testes trocar a IA por um extrator fixo sem monkeypatch.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.rotas import roteador
from app.config import AVISO, Config, obter_config
from app.db.modelos import Base
from app.db.repositorio import Repositorio, RepositorioNulo, RepositorioSQL
from app.erros import ErroLupa, LimiteExcedido
from app.llm.base import Extrator
from app.llm.cadeia import Cadeia
from app.llm.compat_openai import ProvedorOpenAICompat
from app.llm.heuristico import ExtratorHeuristico
from app.logs import configurar_logs
from app.servicos.analise import ServicoAnalise
from app.servicos.cache import CacheTTL
from app.servicos.limites import Limites

log = logging.getLogger("lupa")


def montar_extratores(config: Config, cliente: httpx.AsyncClient) -> list[Extrator]:
    """Groq -> Gemini -> heurística, pulando quem não tem chave."""
    extratores: list[Extrator] = []
    if config.groq_api_key:
        extratores.append(
            ProvedorOpenAICompat(
                "groq",
                config.groq_url,
                config.groq_modelo,
                config.groq_api_key.get_secret_value(),
                cliente,
            )
        )
    if config.gemini_api_key:
        # O endpoint compatível do Gemini não aceita additionalProperties no schema.
        extratores.append(
            ProvedorOpenAICompat(
                "gemini",
                config.gemini_url,
                config.gemini_modelo,
                config.gemini_api_key.get_secret_value(),
                cliente,
                estrito=False,
                additional_properties=False,
            )
        )
    extratores.append(ExtratorHeuristico())
    return extratores


def montar_repositorio(config: Config) -> Repositorio:
    if not config.database_url:
        return RepositorioNulo()
    repositorio = RepositorioSQL.de_url(config.database_url)
    if config.database_url.startswith("sqlite"):
        # Conveniência de desenvolvimento. Em produção (PostgreSQL) quem cria
        # as tabelas são as migrações do Alembic, rodadas antes do servidor subir.
        Base.metadata.create_all(repositorio.engine)
    return repositorio


def _erro(status: int, codigo: str, mensagem: str, **cabecalhos: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": {"codigo": codigo, "mensagem": mensagem}},
        headers=cabecalhos or None,
    )


def criar_app(
    config: Config | None = None,
    *,
    extratores: list[Extrator] | None = None,
    repositorio: Repositorio | None = None,
) -> FastAPI:
    config = config or obter_config()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient() as cliente:
            cadeia = Cadeia(extratores or montar_extratores(config, cliente))
            app.state.config = config
            app.state.repositorio = repositorio or montar_repositorio(config)
            app.state.limites = Limites(
                config.limite_por_ip, config.janela_ip_segundos, config.limite_diario
            )
            app.state.servico = ServicoAnalise(
                cadeia,
                app.state.repositorio,
                CacheTTL(config.cache_ttl_segundos, config.cache_max_itens),
                max_caracteres=config.max_caracteres,
                max_clausulas=config.max_clausulas,
            )
            app.state.provedores = [e.nome for e in cadeia.extratores]
            log.info("app_iniciada", extra={"provedores": app.state.provedores})
            yield

    app = FastAPI(
        title="Lupa do Aluguel",
        version=__version__,
        description=f"Aponta cláusulas abusivas em contratos de aluguel residencial. {AVISO}",
        lifespan=ciclo_de_vida,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origens,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-Id", "Retry-After"],
    )

    @app.middleware("http")
    async def registrar_requisicao(
        request: Request, seguir: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        pedido_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        inicio = time.perf_counter()
        resposta = await seguir(request)
        resposta.headers["X-Request-Id"] = pedido_id
        log.info(
            "requisicao",
            extra={
                "pedido_id": pedido_id,
                "metodo": request.method,
                "rota": request.url.path,
                "status": resposta.status_code,
                "ms": round((time.perf_counter() - inicio) * 1000),
            },
        )
        return resposta

    @app.exception_handler(ErroLupa)
    async def tratar_erro_lupa(_: Request, erro: ErroLupa) -> JSONResponse:
        cabecalhos = {}
        if isinstance(erro, LimiteExcedido):
            cabecalhos["Retry-After"] = str(erro.tentar_em_segundos)
        return _erro(erro.status, erro.codigo, erro.mensagem, **cabecalhos)

    @app.exception_handler(RequestValidationError)
    async def tratar_validacao(_: Request, erro: RequestValidationError) -> JSONResponse:
        campos = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "corpo" for e in erro.errors())
        return _erro(422, "entrada_invalida", f"Requisição inválida ({campos}).")

    @app.exception_handler(Exception)
    async def tratar_inesperado(_: Request, erro: Exception) -> JSONResponse:
        log.exception("erro_inesperado")
        return _erro(500, "erro_interno", "Erro inesperado. Tente de novo em instantes.")

    @app.get("/health", tags=["infra"])
    async def saude(request: Request) -> dict[str, object]:
        return {"status": "ok", "versao": __version__, "provedores": request.app.state.provedores}

    app.include_router(roteador)
    return app


def app_producao() -> FastAPI:
    """Ponto de entrada do uvicorn (`--factory`)."""
    configurar_logs()
    return criar_app()

"""Rotas HTTP. Finas: validam a entrada, aplicam limites e delegam ao serviço."""

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import Config
from app.db.repositorio import Repositorio
from app.dominio.modelos import Relatorio
from app.dominio.regras import REGRAS
from app.entrada.pdf import extrair_texto
from app.erros import ConsentimentoAusente, EntradaInvalida
from app.servicos.analise import ServicoAnalise
from app.servicos.limites import Limites

roteador = APIRouter(prefix="/v1")


class PedidoAnalise(BaseModel):
    texto: str = Field(min_length=1, max_length=200_000, description="Texto do contrato.")
    consentimento: bool = Field(
        False,
        description="O usuário leu o aviso de privacidade e consentiu com o envio do texto "
        "ao provedor de IA (LGPD, art. 7º, I). Sem isso a análise é recusada.",
    )


class RegraPublica(BaseModel):
    id: int
    titulo: str
    artigo: str
    descricao: str
    orientacao: str


def ip_do_cliente(request: Request) -> str:
    # Atrás do proxy do Render, o IP real é o último item que o proxy acrescenta
    # ao X-Forwarded-For; os anteriores podem ter sido forjados pelo cliente.
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[-1].strip()
    return request.client.host if request.client else "desconhecido"


def _exigir_consentimento(consentimento: bool) -> None:
    """O consentimento é checado no servidor: a caixa da página sozinha não basta."""
    if not consentimento:
        raise ConsentimentoAusente(
            "Para analisar, é preciso concordar com o envio do texto. Veja o aviso de privacidade."
        )


def _servico(request: Request) -> ServicoAnalise:
    servico: ServicoAnalise = request.app.state.servico
    return servico


def _limitar(request: Request) -> None:
    limites: Limites = request.app.state.limites
    limites.verificar(ip_do_cliente(request))


@roteador.post("/analises", response_model=Relatorio, summary="Analisa o texto de um contrato")
async def analisar_texto(pedido: PedidoAnalise, request: Request) -> Relatorio:
    _exigir_consentimento(pedido.consentimento)
    _limitar(request)
    return await _servico(request).analisar(pedido.texto, origem="texto")


@roteador.post("/analises/pdf", response_model=Relatorio, summary="Analisa um contrato em PDF")
async def analisar_pdf(
    request: Request,
    arquivo: Annotated[UploadFile, File()],
    consentimento: Annotated[bool, Form()] = False,
) -> Relatorio:
    _exigir_consentimento(consentimento)
    config: Config = request.app.state.config
    conteudo = await arquivo.read(config.max_pdf_bytes + 1)
    if len(conteudo) > config.max_pdf_bytes:
        limite_mb = config.max_pdf_bytes // 1_000_000
        raise EntradaInvalida(f"O PDF passa de {limite_mb} MB.")
    _limitar(request)
    texto = await run_in_threadpool(extrair_texto, conteudo, config.max_paginas)
    return await _servico(request).analisar(texto, origem="pdf")


@roteador.get("/regras", response_model=list[RegraPublica], summary="As 7 regras verificadas")
async def listar_regras() -> list[RegraPublica]:
    return [RegraPublica(**r.__dict__) for r in REGRAS]


@roteador.get("/estatisticas", summary="Métricas de uso agregadas (sem conteúdo de contratos)")
async def estatisticas(
    request: Request, dias: Annotated[int, Query(ge=1, le=365)] = 30
) -> dict[str, Any]:
    repositorio: Repositorio = request.app.state.repositorio
    return await run_in_threadpool(repositorio.estatisticas, dias)

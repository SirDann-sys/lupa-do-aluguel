"""Orquestra uma análise: texto -> cláusulas -> fatos -> provas -> regras -> relatório.

    mascarar dados pessoais -> hash -> cache? -> dividir -> extrair (cadeia de provedores)
               -> validar evidências -> avaliar regras -> relatório -> métrica

O texto do contrato só existe em memória durante a requisição (e no cache em
memória). O banco recebe apenas números: latência, provedor, regras violadas.
"""

import hashlib
import logging
import time
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool

from app.config import AVISO
from app.db.repositorio import NovaExecucao, Repositorio
from app.dominio import evidencias, regras
from app.dominio.modelos import ClausulaRelatorio, FatosClausula, Relatorio
from app.entrada.anonimizar import mascarar
from app.entrada.divisor import dividir
from app.erros import EntradaInvalida, ErroLupa
from app.llm.base import Extracao
from app.llm.cadeia import Cadeia
from app.servicos.cache import CacheTTL

log = logging.getLogger(__name__)


def chave_de_cache(texto: str) -> str:
    return hashlib.sha256(" ".join(texto.split()).encode()).hexdigest()


def _alinhar(extracao: Extracao, clausulas: list[str]) -> tuple[list[FatosClausula], int]:
    """Um conjunto de fatos validado por cláusula, na ordem; ignora índices inventados."""
    por_indice = {f.indice: f for f in extracao.fatos if 1 <= f.indice <= len(clausulas)}
    fatos: list[FatosClausula] = []
    descartados = 0
    for indice, texto in enumerate(clausulas, start=1):
        bruto = por_indice.get(indice, FatosClausula(indice=indice))
        limpo, campos = evidencias.validar(bruto, texto)
        descartados += len(campos)
        fatos.append(limpo)
    return fatos, descartados


class ServicoAnalise:
    def __init__(
        self,
        cadeia: Cadeia,
        repositorio: Repositorio,
        cache: CacheTTL[Relatorio],
        *,
        max_caracteres: int,
        max_clausulas: int,
        relogio: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._cadeia = cadeia
        self._repositorio = repositorio
        self._cache = cache
        self._max_caracteres = max_caracteres
        self._max_clausulas = max_clausulas
        self._relogio = relogio

    async def analisar(self, texto: str, origem: str = "texto") -> Relatorio:
        inicio = self._relogio()
        try:
            relatorio, extracao = await self._analisar(texto)
        except ErroLupa as erro:
            await self._registrar(
                NovaExecucao(origem=origem, status=erro.codigo, latencia_ms=self._ms(inicio))
            )
            raise

        await self._registrar(
            NovaExecucao(
                origem=origem,
                status="ok",
                latencia_ms=self._ms(inicio),
                provedor=relatorio.provedor,
                modelo=relatorio.modelo,
                em_cache=relatorio.em_cache,
                usou_reserva=bool(extracao and extracao.falhas),
                clausulas=len(relatorio.clausulas),
                regras_violadas=tuple(sorted({a.regra for a in relatorio.achados})),
                fatos_descartados=relatorio.fatos_descartados,
                tokens_entrada=extracao.tokens_entrada if extracao else 0,
                tokens_saida=extracao.tokens_saida if extracao else 0,
            )
        )
        return relatorio

    async def _analisar(self, texto: str) -> tuple[Relatorio, Extracao | None]:
        texto = texto.strip()
        if not texto:
            raise EntradaInvalida("Cole o texto do contrato.")
        if len(texto) > self._max_caracteres:
            raise EntradaInvalida(
                f"O texto tem {len(texto):,} caracteres; o limite é "
                f"{self._max_caracteres:,}.".replace(",", ".")
            )

        texto, mascarados = mascarar(texto)
        chave = chave_de_cache(texto)
        if (em_cache := self._cache.obter(chave)) is not None:
            return em_cache.model_copy(update={"em_cache": True}), None

        clausulas = dividir(texto)
        if not clausulas:
            raise EntradaInvalida(
                "Não encontrei cláusulas no texto. Confira se ele é mesmo um contrato, "
                "com cláusulas separadas por parágrafo ou numeradas."
            )
        if len(clausulas) > self._max_clausulas:
            raise EntradaInvalida(
                f"O contrato tem {len(clausulas)} cláusulas; o limite é {self._max_clausulas}."
            )

        extracao = await self._cadeia.extrair(clausulas)
        fatos, descartados = _alinhar(extracao, clausulas)
        achados = regras.avaliar(fatos)

        regras_por_clausula: dict[int, set[int]] = {}
        for achado in achados:
            for indice in achado.clausulas:
                regras_por_clausula.setdefault(indice, set()).add(achado.regra)

        relatorio = Relatorio(
            clausulas=[
                ClausulaRelatorio(indice=i, texto=t, regras=sorted(regras_por_clausula.get(i, ())))
                for i, t in enumerate(clausulas, start=1)
            ],
            achados=achados,
            provedor=extracao.provedor,
            modelo=extracao.modelo,
            fatos_descartados=descartados,
            dados_mascarados=mascarados,
            aviso=AVISO,
        )
        # Resultado vindo de uma reserva (o provedor principal falhou) não entra no
        # cache: senão o mesmo contrato ficaria preso à análise pior por 24 h.
        if not extracao.falhas:
            self._cache.guardar(chave, relatorio)
        log.info(
            "analise_concluida",
            extra={
                "provedor": extracao.provedor,
                "clausulas": len(clausulas),
                "achados": len(achados),
                "descartados": descartados,
            },
        )
        return relatorio, extracao

    async def _registrar(self, execucao: NovaExecucao) -> None:
        await run_in_threadpool(self._repositorio.registrar, execucao)

    def _ms(self, inicio: float) -> int:
        return round((self._relogio() - inicio) * 1000)

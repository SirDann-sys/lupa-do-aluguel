"""Cadeia de extratores: tenta o primeiro, repete em falha temporária, cai para o próximo.

A ordem típica é Groq -> Gemini -> heurística. O último elo (heurística) não
depende de rede, então a análise quase sempre sai; o relatório diz qual
provedor respondeu, para o usuário saber a precisão esperada.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

from app.erros import ProvedoresIndisponiveis
from app.llm.base import ErroProvedor, Extracao, Extrator

log = logging.getLogger(__name__)

Dormir = Callable[[float], Awaitable[None]]


class Cadeia:
    def __init__(
        self,
        extratores: Sequence[Extrator],
        *,
        tentativas: int = 2,
        espera_base: float = 1.0,
        espera_maxima: float = 8.0,
        dormir: Dormir = asyncio.sleep,
    ) -> None:
        if not extratores:
            raise ValueError("A cadeia precisa de pelo menos um extrator.")
        self.extratores = list(extratores)
        self._tentativas = tentativas
        self._espera_base = espera_base
        self._espera_maxima = espera_maxima
        self._dormir = dormir

    async def extrair(self, clausulas: list[str]) -> Extracao:
        falhas: list[str] = []
        for extrator in self.extratores:
            for tentativa in range(self._tentativas):
                try:
                    extracao = await extrator.extrair(clausulas)
                except ErroProvedor as erro:
                    falhas.append(str(erro))
                    log.warning(
                        "extrator_falhou",
                        extra={"provedor": extrator.nome, "temporario": erro.temporario},
                    )
                    espera = self._espera(erro, tentativa)
                    ultima = tentativa == self._tentativas - 1
                    if not erro.temporario or ultima or espera is None:
                        break
                    await self._dormir(espera)
                else:
                    return replace(extracao, falhas=falhas)
        raise ProvedoresIndisponiveis(
            "Nenhum provedor de análise respondeu agora. Tente de novo em alguns minutos."
        )

    def _espera(self, erro: ErroProvedor, tentativa: int) -> float | None:
        """Quanto esperar antes de repetir; None = não vale esperar, passe ao próximo."""
        espera = erro.espera if erro.espera is not None else self._espera_base * 2**tentativa
        return espera if espera <= self._espera_maxima else None

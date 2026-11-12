"""Limites de uso: por IP (janela deslizante) e global por dia.

O limite diário protege a cota gratuita dos provedores de IA: um único
visitante insistente não pode consumir a cota do dia de todos os outros.
Em memória, o que basta para uma única instância.
"""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.erros import LimiteExcedido


class Limites:
    def __init__(
        self,
        por_ip: int,
        janela_segundos: float,
        por_dia: int,
        relogio: Callable[[], float] = time.monotonic,
        hoje: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self._por_ip = por_ip
        self._janela = janela_segundos
        self._por_dia = por_dia
        self._relogio = relogio
        self._hoje = hoje
        self._acessos: defaultdict[str, deque[float]] = defaultdict(deque)
        self._dia = hoje()
        self._total_dia = 0

    def verificar(self, ip: str) -> None:
        """Registra o uso ou levanta `LimiteExcedido`."""
        agora = self._relogio()
        if self._hoje() != self._dia:
            self._dia, self._total_dia = self._hoje(), 0
            self._acessos.clear()  # evita acumular IPs antigos para sempre
        if self._total_dia >= self._por_dia:
            raise LimiteExcedido(
                "O limite diário de análises gratuitas foi atingido. Volte amanhã.",
                tentar_em_segundos=3600,
            )

        acessos = self._acessos[ip]
        while acessos and agora - acessos[0] >= self._janela:
            acessos.popleft()
        if len(acessos) >= self._por_ip:
            espera = math.ceil(self._janela - (agora - acessos[0]))
            raise LimiteExcedido(
                f"Muitas análises seguidas. Tente de novo em {espera} segundos.",
                tentar_em_segundos=espera,
            )

        acessos.append(agora)
        self._total_dia += 1

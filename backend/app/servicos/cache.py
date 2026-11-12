"""Cache em memória com validade (TTL) e limite de itens (LRU).

Fica em memória de propósito: o resultado contém trechos do contrato, e o
contrato não deve ir para disco. Reiniciar o servidor apaga tudo.
"""

import time
from collections import OrderedDict
from collections.abc import Callable


class CacheTTL[V]:
    def __init__(
        self, ttl_segundos: float, max_itens: int, relogio: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_segundos
        self._max = max_itens
        self._relogio = relogio
        self._itens: OrderedDict[str, tuple[float, V]] = OrderedDict()

    def obter(self, chave: str) -> V | None:
        item = self._itens.get(chave)
        if item is None:
            return None
        expira, valor = item
        if self._relogio() >= expira:
            del self._itens[chave]
            return None
        self._itens.move_to_end(chave)
        return valor

    def guardar(self, chave: str, valor: V) -> None:
        self._itens[chave] = (self._relogio() + self._ttl, valor)
        self._itens.move_to_end(chave)
        while len(self._itens) > self._max:
            self._itens.popitem(last=False)

    def __len__(self) -> int:
        return len(self._itens)

"""Logs em JSON, uma linha por evento, prontos para o painel do Render."""

import json
import logging
from datetime import UTC, datetime

_CAMPOS_PADRAO = set(vars(logging.makeLogRecord({})))


class FormatoJSON(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        dados = {
            "quando": datetime.fromtimestamp(registro.created, UTC).isoformat(),
            "nivel": registro.levelname,
            "evento": registro.getMessage(),
            "origem": registro.name,
        }
        dados.update({k: v for k, v in vars(registro).items() if k not in _CAMPOS_PADRAO})
        if registro.exc_info:
            dados["erro"] = self.formatException(registro.exc_info)
        return json.dumps(dados, ensure_ascii=False, default=str)


def configurar_logs(nivel: int = logging.INFO) -> None:
    saida = logging.StreamHandler()
    saida.setFormatter(FormatoJSON())
    raiz = logging.getLogger()
    raiz.handlers[:] = [saida]
    raiz.setLevel(nivel)

import json
import logging

import pytest

from app.logs import FormatoJSON, configurar_logs


def test_log_em_json_com_campos_extras() -> None:
    registro = logging.makeLogRecord(
        {"msg": "analise_concluida", "levelname": "INFO", "name": "lupa", "provedor": "groq"}
    )
    dados = json.loads(FormatoJSON().format(registro))
    assert dados["evento"] == "analise_concluida"
    assert dados["provedor"] == "groq"
    assert dados["nivel"] == "INFO"


def test_log_inclui_a_excecao() -> None:
    try:
        raise ValueError("falhou")
    except ValueError:
        registro = logging.LogRecord(
            "lupa", logging.ERROR, __file__, 1, "erro", None, exc_info=__import__("sys").exc_info()
        )
    assert "ValueError: falhou" in json.loads(FormatoJSON().format(registro))["erro"]


def test_configurar_logs_troca_o_formato(monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = logging.getLogger()
    monkeypatch.setattr(raiz, "handlers", list(raiz.handlers))
    configurar_logs()
    assert isinstance(raiz.handlers[0].formatter, FormatoJSON)

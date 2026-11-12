from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.config import Config
from app.main import criar_app, montar_extratores
from tests.conftest import CONTRATO_CURTO, ExtratorFixo, caucao_cinco_meses


def test_health_lista_os_provedores(cliente: TestClient) -> None:
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["provedores"] == ["fixo"]
    assert resposta.headers["x-request-id"]


def test_lista_as_sete_regras(cliente: TestClient) -> None:
    regras = cliente.get("/v1/regras").json()
    assert [r["id"] for r in regras] == [1, 2, 3, 4, 5, 6, 7]
    assert all(r["artigo"] and r["orientacao"] for r in regras)


def test_analisa_texto(cliente: TestClient) -> None:
    resposta = cliente.post("/v1/analises", json={"texto": CONTRATO_CURTO})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [a["regra"] for a in corpo["achados"]] == [1]
    assert corpo["achados"][0]["trechos"]
    assert len(corpo["clausulas"]) == 3
    assert corpo["aviso"]


def _pdf(texto: str) -> bytes:
    saida = BytesIO()
    tela = Canvas(saida, pagesize=A4)
    objeto = tela.beginText(40, 800)
    for linha in texto.splitlines():
        objeto.textLine(linha)
    tela.drawText(objeto)
    tela.showPage()
    tela.save()
    return saida.getvalue()


def test_analisa_pdf(cliente: TestClient) -> None:
    arquivo = {"arquivo": ("contrato.pdf", _pdf(CONTRATO_CURTO), "application/pdf")}
    resposta = cliente.post("/v1/analises/pdf", files=arquivo)
    assert resposta.status_code == 200
    assert [a["regra"] for a in resposta.json()["achados"]] == [1]


def test_pdf_grande_demais(config: Config) -> None:
    config.max_pdf_bytes = 100
    app = criar_app(config, extratores=[ExtratorFixo(construir=caucao_cinco_meses)])
    with TestClient(app) as cliente:
        arquivo = {"arquivo": ("c.pdf", b"%PDF-" + b"0" * 200, "application/pdf")}
        resposta = cliente.post("/v1/analises/pdf", files=arquivo)
    assert resposta.status_code == 422
    assert resposta.json()["erro"]["codigo"] == "entrada_invalida"


def test_arquivo_que_nao_e_pdf(cliente: TestClient) -> None:
    arquivo = {"arquivo": ("c.pdf", b"isto nao e pdf", "application/pdf")}
    resposta = cliente.post("/v1/analises/pdf", files=arquivo)
    assert resposta.status_code == 415
    assert resposta.json()["erro"]["codigo"] == "arquivo_invalido"


def test_corpo_invalido_tem_erro_padronizado(cliente: TestClient) -> None:
    resposta = cliente.post("/v1/analises", json={"contrato": "campo errado"})
    assert resposta.status_code == 422
    assert resposta.json()["erro"]["codigo"] == "entrada_invalida"
    assert "texto" in resposta.json()["erro"]["mensagem"]


def test_texto_sem_clausulas(cliente: TestClient) -> None:
    resposta = cliente.post("/v1/analises", json={"texto": "oi"})
    assert resposta.status_code == 422
    assert "cláusulas" in resposta.json()["erro"]["mensagem"]


def test_limite_por_ip_devolve_429_com_retry_after(cliente: TestClient) -> None:
    cabecalho = {"X-Forwarded-For": "8.8.8.8, 10.0.0.1"}
    for _ in range(3):
        assert (
            cliente.post(
                "/v1/analises", json={"texto": CONTRATO_CURTO}, headers=cabecalho
            ).status_code
            == 200
        )
    resposta = cliente.post("/v1/analises", json={"texto": CONTRATO_CURTO}, headers=cabecalho)
    assert resposta.status_code == 429
    assert int(resposta.headers["retry-after"]) > 0
    # outro IP real (último item do X-Forwarded-For) continua livre
    outro = cliente.post(
        "/v1/analises",
        json={"texto": CONTRATO_CURTO},
        headers={"X-Forwarded-For": "8.8.8.8, 10.0.0.2"},
    )
    assert outro.status_code == 200


def test_estatisticas_contam_as_analises(cliente: TestClient) -> None:
    cliente.post("/v1/analises", json={"texto": CONTRATO_CURTO})
    cliente.post("/v1/analises", json={"texto": "oi"})
    dados = cliente.get("/v1/estatisticas?dias=7").json()
    assert dados["analises"] == 1
    assert dados["erros"] == 1
    assert dados["por_provedor"] == {"fixo": 1}
    assert dados["regras_mais_violadas"] == {"1": 1}


def test_estatisticas_valida_o_periodo(cliente: TestClient) -> None:
    assert cliente.get("/v1/estatisticas?dias=0").status_code == 422


def test_cors_libera_so_as_origens_configuradas(cliente: TestClient) -> None:
    liberada = cliente.options(
        "/v1/analises",
        headers={
            "Origin": "https://sirdann-sys.github.io",
            "Access-Control-Request-Method": "POST",
        },
    )
    bloqueada = cliente.options(
        "/v1/analises",
        headers={"Origin": "https://site-qualquer.com", "Access-Control-Request-Method": "POST"},
    )
    assert liberada.headers["access-control-allow-origin"] == "https://sirdann-sys.github.io"
    assert "access-control-allow-origin" not in bloqueada.headers


def test_erro_inesperado_nao_vaza_detalhes(config: Config) -> None:
    class Quebrado:
        nome, modelo = "quebrado", "x"

        async def extrair(self, clausulas: list[str]) -> None:
            raise RuntimeError("segredo interno")

    app = criar_app(config, extratores=[Quebrado()])  # type: ignore[list-item]
    with TestClient(app, raise_server_exceptions=False) as cliente:
        resposta = cliente.post("/v1/analises", json={"texto": CONTRATO_CURTO})
    assert resposta.status_code == 500
    assert resposta.json()["erro"]["codigo"] == "erro_interno"
    assert "segredo" not in resposta.text


def test_sem_chaves_a_cadeia_e_so_a_heuristica(config: Config) -> None:
    import httpx

    nomes = [e.nome for e in montar_extratores(config, httpx.AsyncClient())]
    assert nomes == ["heuristico"]


def test_com_chaves_a_ordem_e_groq_gemini_heuristica(config: Config) -> None:
    import httpx

    config = Config(**{**config.model_dump(), "groq_api_key": "g", "gemini_api_key": "m"})
    nomes = [e.nome for e in montar_extratores(config, httpx.AsyncClient())]
    assert nomes == ["groq", "gemini", "heuristico"]


def test_sem_banco_as_metricas_ficam_desligadas(tmp_path: Path) -> None:
    config = Config(_env_file=None, database_url=None)
    app = criar_app(config, extratores=[ExtratorFixo(construir=caucao_cinco_meses)])
    with TestClient(app) as cliente:
        cliente.post("/v1/analises", json={"texto": CONTRATO_CURTO})
        assert cliente.get("/v1/estatisticas").json()["analises"] == 0

import json
from typing import Any

import httpx
import pytest

from app.dominio.modelos import RespostaExtracao, TipoGarantia
from app.erros import ProvedoresIndisponiveis
from app.llm.base import ErroProvedor
from app.llm.cadeia import Cadeia
from app.llm.compat_openai import ProvedorOpenAICompat
from app.llm.esquema import esquema_estrito
from app.llm.heuristico import ExtratorHeuristico, extrair_clausula
from app.llm.prompt import mensagem_usuario
from tests.conftest import ExtratorFixo, fatos

# ---------------------------------------------------------------- esquema


def _objetos(no: Any) -> list[dict[str, Any]]:
    if isinstance(no, list):
        return [o for item in no for o in _objetos(item)]
    if not isinstance(no, dict):
        return []
    proprios = [no] if no.get("type") == "object" else []
    return proprios + [o for valor in no.values() for o in _objetos(valor)]


def test_esquema_estrito_cumpre_as_exigencias_do_modo_estrito() -> None:
    esquema = esquema_estrito(RespostaExtracao)
    texto = json.dumps(esquema)
    assert "$ref" not in texto
    assert '"title"' not in texto
    assert '"default"' not in texto
    for objeto in _objetos(esquema):
        assert objeto["additionalProperties"] is False
        assert set(objeto["required"]) == set(objeto["properties"])


def test_esquema_opcional_vira_tipo_anulavel() -> None:
    item = esquema_estrito(RespostaExtracao)["properties"]["clausulas"]["items"]
    assert item["properties"]["caucao_meses"]["type"] == ["number", "null"]
    assert item["properties"]["reajuste_periodicidade_meses"]["type"] == ["integer", "null"]
    assert set(item["properties"]["garantias"]["items"]["enum"]) == set(TipoGarantia)


def test_esquema_sem_additional_properties_para_o_gemini() -> None:
    texto = json.dumps(esquema_estrito(RespostaExtracao, additional_properties=False))
    assert "additionalProperties" not in texto


def test_mensagem_numera_as_clausulas() -> None:
    assert "[1] primeira" in mensagem_usuario(["primeira", "segunda"])
    assert "[2] segunda" in mensagem_usuario(["primeira", "segunda"])


# ---------------------------------------------------------------- provedor HTTP

RESPOSTA_OK = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "clausulas": [
                            {
                                "indice": 1,
                                "garantias": ["fiador"],
                                "caucao_meses": None,
                                "caucao_valor": None,
                                "aluguel_mensal": None,
                                "aluguel_antecipado_meses": None,
                                "aluguel_antecipado_valor": None,
                                "reajuste_periodicidade_meses": None,
                                "inquilino_paga_despesas_extraordinarias": False,
                                "inquilino_paga_taxa_imobiliaria": False,
                                "pintura_obrigatoria_incondicional": False,
                                "evidencias": [{"campo": "garantias", "trecho": "fiador"}],
                            },
                        ]
                    }
                )
            }
        }
    ],
    "usage": {"prompt_tokens": 321, "completion_tokens": 45},
}


def _provedor(responder: Any, **opcoes: Any) -> ProvedorOpenAICompat:
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return ProvedorOpenAICompat(
        "groq", "https://api.teste/v1/", "modelo-x", "chave-x", cliente, **opcoes
    )


async def test_provedor_envia_schema_estrito_e_le_a_resposta() -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json=RESPOSTA_OK)

    extracao = await _provedor(responder).extrair(["O LOCATÁRIO apresenta fiador."])

    [pedido] = pedidos
    corpo = json.loads(pedido.content)
    assert str(pedido.url) == "https://api.teste/v1/chat/completions"
    assert pedido.headers["authorization"] == "Bearer chave-x"
    assert corpo["model"] == "modelo-x"
    assert corpo["temperature"] == 0
    assert corpo["response_format"]["json_schema"]["strict"] is True
    assert extracao.fatos[0].garantias == [TipoGarantia.FIADOR]
    assert (extracao.tokens_entrada, extracao.tokens_saida) == (321, 45)
    assert (extracao.provedor, extracao.modelo) == ("groq", "modelo-x")


async def test_provedor_modo_nao_estrito() -> None:
    corpos: list[dict[str, Any]] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        corpos.append(json.loads(pedido.content))
        return httpx.Response(200, json=RESPOSTA_OK)

    await _provedor(responder, estrito=False).extrair(["x"])
    assert corpos[0]["response_format"]["json_schema"]["strict"] is False


@pytest.mark.parametrize(
    ("resposta", "temporario", "espera"),
    [
        (httpx.Response(429, headers={"retry-after": "7"}), True, 7.0),
        (httpx.Response(429, headers={"retry-after": "depois"}), True, None),
        (httpx.Response(503), True, None),
        (httpx.Response(401), False, None),
        (httpx.Response(200, json={"choices": []}), True, None),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": "não é json"}}]}),
            True,
            None,
        ),
        (httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1}'}}]}), True, None),
    ],
)
async def test_provedor_classifica_falhas(
    resposta: httpx.Response, temporario: bool, espera: float | None
) -> None:
    with pytest.raises(ErroProvedor) as erro:
        await _provedor(lambda _: resposta).extrair(["x"])
    assert erro.value.temporario is temporario
    assert erro.value.espera == espera


@pytest.mark.parametrize("excecao", [httpx.ReadTimeout("lento"), httpx.ConnectError("sem rede")])
async def test_provedor_falha_de_rede_e_temporaria(excecao: Exception) -> None:
    def responder(_: httpx.Request) -> httpx.Response:
        raise excecao

    with pytest.raises(ErroProvedor) as erro:
        await _provedor(responder).extrair(["x"])
    assert erro.value.temporario


# ---------------------------------------------------------------- cadeia


class Relogio:
    def __init__(self) -> None:
        self.esperas: list[float] = []

    async def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def _temporario(nome: str = "a", espera: float | None = None) -> ErroProvedor:
    return ErroProvedor(nome, "fora do ar", temporario=True, espera=espera)


async def test_cadeia_usa_o_primeiro_que_responde() -> None:
    primeiro = ExtratorFixo("a", [[fatos(1)]])
    segundo = ExtratorFixo("b", [[fatos(1)]])
    extracao = await Cadeia([primeiro, segundo]).extrair(["x"])
    assert extracao.provedor == "a"
    assert extracao.falhas == []
    assert segundo.chamadas == 0


async def test_cadeia_repete_falha_temporaria_com_backoff() -> None:
    relogio = Relogio()
    extrator = ExtratorFixo("a", [_temporario(), _temporario(), [fatos(1)]])
    cadeia = Cadeia([extrator], tentativas=3, espera_base=0.5, dormir=relogio)
    extracao = await cadeia.extrair(["x"])
    assert extracao.provedor == "a"
    assert relogio.esperas == [0.5, 1.0]
    assert len(extracao.falhas) == 2


async def test_cadeia_respeita_retry_after_do_provedor() -> None:
    relogio = Relogio()
    extrator = ExtratorFixo("a", [_temporario(espera=3), [fatos(1)]])
    await Cadeia([extrator], dormir=relogio).extrair(["x"])
    assert relogio.esperas == [3]


async def test_cadeia_nao_espera_demais_e_passa_ao_proximo() -> None:
    relogio = Relogio()
    lento = ExtratorFixo("a", [_temporario(espera=60)])
    reserva = ExtratorFixo("b", [[fatos(1)]])
    extracao = await Cadeia([lento, reserva], dormir=relogio).extrair(["x"])
    assert extracao.provedor == "b"
    assert relogio.esperas == []
    assert extracao.falhas == ["a: fora do ar"]


async def test_cadeia_nao_repete_falha_permanente() -> None:
    quebrado = ExtratorFixo("a", [ErroProvedor("a", "chave inválida", temporario=False)])
    reserva = ExtratorFixo("b", [[fatos(1)]])
    extracao = await Cadeia([quebrado, reserva], dormir=Relogio()).extrair(["x"])
    assert quebrado.chamadas == 1
    assert extracao.provedor == "b"


async def test_cadeia_sem_ninguem_respondendo() -> None:
    cadeia = Cadeia([ExtratorFixo("a", [_temporario(), _temporario()])], dormir=Relogio())
    with pytest.raises(ProvedoresIndisponiveis):
        await cadeia.extrair(["x"])


def test_cadeia_vazia_e_erro_de_programacao() -> None:
    with pytest.raises(ValueError, match="pelo menos um"):
        Cadeia([])


# ---------------------------------------------------------------- heurística


@pytest.mark.parametrize(
    ("clausula", "esperado"),
    [
        (
            "O aluguel mensal é de R$ 2.500,00 (dois mil e quinhentos reais).",
            {"aluguel_mensal": 2500.0},
        ),
        (
            "O LOCATÁRIO prestará caução em dinheiro equivalente a 4 (quatro) aluguéis.",
            {"caucao_meses": 4.0, "garantias": ["caucao"]},
        ),
        (
            "Como garantia, o LOCATÁRIO fará depósito de R$ 7.000,00.",
            {"caucao_valor": 7000.0, "garantias": ["caucao"]},
        ),
        (
            "O LOCATÁRIO pagará antecipadamente o equivalente a um mês de aluguel.",
            {"aluguel_antecipado_meses": 1.0},
        ),
        (
            "O aluguel será reajustado semestralmente pelo IGP-M.",
            {"reajuste_periodicidade_meses": 6},
        ),
        ("O aluguel será reajustado a cada 3 (três) meses.", {"reajuste_periodicidade_meses": 3}),
        (
            "O LOCATÁRIO arcará com as despesas extraordinárias do condomínio.",
            {"inquilino_paga_despesas_extraordinarias": True},
        ),
        (
            "O LOCATÁRIO pagará taxa de administração à imobiliária.",
            {"inquilino_paga_taxa_imobiliaria": True},
        ),
        (
            "Entregará o imóvel pintado, independentemente do estado.",
            {"pintura_obrigatoria_incondicional": True},
        ),
        (
            "O LOCATÁRIO apresenta fiador e contrata seguro-fiança.",
            {"garantias": ["fiador", "seguro_fianca"]},
        ),
    ],
)
def test_heuristica_extrai_fatos(clausula: str, esperado: dict[str, Any]) -> None:
    obtido = extrair_clausula(1, clausula).model_dump()
    for campo, valor in esperado.items():
        assert obtido[campo] == valor
    assert obtido["evidencias"], "todo fato afirmado precisa de evidência"


@pytest.mark.parametrize(
    "clausula",
    [
        "As despesas extraordinárias permanecem sob responsabilidade do LOCADOR.",
        "Em caso de rescisão antecipada, multa de 3 meses de aluguel.",
        "Apresenta fiador, não sendo exigida nenhuma outra caução.",
    ],
)
def test_heuristica_nao_inventa(clausula: str) -> None:
    obtido = extrair_clausula(1, clausula)
    assert not obtido.inquilino_paga_despesas_extraordinarias
    assert obtido.aluguel_antecipado_meses is None
    assert "caucao" not in obtido.garantias


async def test_extrator_heuristico_numera_as_clausulas() -> None:
    extracao = await ExtratorHeuristico().extrair(["um texto qualquer", "outro texto"])
    assert [f.indice for f in extracao.fatos] == [1, 2]
    assert extracao.provedor == "heuristico"

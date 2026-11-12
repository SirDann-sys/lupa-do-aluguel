from datetime import date

import pytest

from app.dominio.modelos import Campo
from app.erros import EntradaInvalida, LimiteExcedido, ProvedoresIndisponiveis
from app.llm.base import ErroProvedor
from app.llm.cadeia import Cadeia
from app.servicos.analise import ServicoAnalise, chave_de_cache
from app.servicos.cache import CacheTTL
from app.servicos.limites import Limites
from tests.conftest import (
    CONTRATO_CURTO,
    ExtratorFixo,
    RepositorioMemoria,
    caucao_cinco_meses,
    fatos,
    prova,
)

# ---------------------------------------------------------------- cache


class Relogio:
    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora


def test_cache_expira() -> None:
    relogio = Relogio()
    cache: CacheTTL[str] = CacheTTL(10, 5, relogio)
    cache.guardar("a", "valor")
    assert cache.obter("a") == "valor"
    relogio.agora = 10
    assert cache.obter("a") is None
    assert len(cache) == 0


def test_cache_descarta_o_menos_usado() -> None:
    cache: CacheTTL[int] = CacheTTL(100, 2)
    cache.guardar("a", 1)
    cache.guardar("b", 2)
    cache.obter("a")
    cache.guardar("c", 3)
    assert (cache.obter("a"), cache.obter("b"), cache.obter("c")) == (1, None, 3)


def test_chave_de_cache_ignora_espacos() -> None:
    assert chave_de_cache("a  b\nc") == chave_de_cache("a b c")


# ---------------------------------------------------------------- limites


def test_limite_por_ip_em_janela_deslizante() -> None:
    relogio = Relogio()
    limites = Limites(por_ip=2, janela_segundos=60, por_dia=100, relogio=relogio)
    limites.verificar("1.1.1.1")
    limites.verificar("1.1.1.1")
    limites.verificar("2.2.2.2")
    with pytest.raises(LimiteExcedido) as erro:
        limites.verificar("1.1.1.1")
    assert erro.value.tentar_em_segundos == 60
    relogio.agora = 60
    limites.verificar("1.1.1.1")


def test_limite_diario_global_renova_no_dia_seguinte() -> None:
    dia = [date(2026, 11, 12)]
    limites = Limites(por_ip=99, janela_segundos=60, por_dia=2, hoje=lambda: dia[0])
    limites.verificar("a")
    limites.verificar("b")
    with pytest.raises(LimiteExcedido, match="diário"):
        limites.verificar("c")
    dia[0] = date(2026, 11, 13)
    limites.verificar("c")


# ---------------------------------------------------------------- serviço de análise


def _servico(
    *extratores: ExtratorFixo, max_clausulas: int = 50
) -> tuple[ServicoAnalise, RepositorioMemoria]:
    repositorio = RepositorioMemoria()
    servico = ServicoAnalise(
        Cadeia(list(extratores), tentativas=1),
        repositorio,
        CacheTTL(60, 10),
        max_caracteres=5_000,
        max_clausulas=max_clausulas,
    )
    return servico, repositorio


async def test_analise_completa() -> None:
    servico, repositorio = _servico(ExtratorFixo(construir=caucao_cinco_meses))
    relatorio = await servico.analisar(CONTRATO_CURTO)

    assert [a.regra for a in relatorio.achados] == [1]
    assert relatorio.clausulas[1].regras == [1]
    assert relatorio.clausulas[0].regras == []
    assert relatorio.provedor == "fixo"
    assert "não deve ser usado para decisões reais" in relatorio.aviso

    [execucao] = repositorio.execucoes
    assert execucao.status == "ok"
    assert execucao.regras_violadas == (1,)
    assert execucao.clausulas == 3
    assert execucao.tokens_entrada == 100


async def test_segunda_analise_igual_vem_do_cache() -> None:
    extrator = ExtratorFixo(construir=caucao_cinco_meses)
    servico, repositorio = _servico(extrator)
    await servico.analisar(CONTRATO_CURTO)
    segundo = await servico.analisar(CONTRATO_CURTO + "\n\n")

    assert segundo.em_cache
    assert extrator.chamadas == 1
    assert [e.em_cache for e in repositorio.execucoes] == [False, True]


async def test_fato_sem_prova_nao_vira_achado() -> None:
    def inventa(clausulas: list[str]) -> list:  # type: ignore[type-arg]
        return [
            fatos(
                1,
                pintura_obrigatoria_incondicional=True,
                evidencias=[prova(Campo.PINTURA_INCONDICIONAL, "pintura nova sempre")],
            )
        ]

    servico, _ = _servico(ExtratorFixo(construir=inventa))
    relatorio = await servico.analisar(CONTRATO_CURTO)
    assert relatorio.achados == []
    assert relatorio.fatos_descartados == 1


async def test_indices_inventados_pelo_modelo_sao_ignorados() -> None:
    def fora_do_contrato(clausulas: list[str]) -> list:  # type: ignore[type-arg]
        return [fatos(99, inquilino_paga_taxa_imobiliaria=True)]

    servico, _ = _servico(ExtratorFixo(construir=fora_do_contrato))
    relatorio = await servico.analisar(CONTRATO_CURTO)
    assert relatorio.achados == []
    assert len(relatorio.clausulas) == 3


async def test_reserva_e_registrada_na_metrica() -> None:
    fora = ExtratorFixo("groq", [ErroProvedor("groq", "429", temporario=True, espera=99)])
    reserva = ExtratorFixo("heuristico", construir=caucao_cinco_meses)
    servico, repositorio = _servico(fora, reserva)
    relatorio = await servico.analisar(CONTRATO_CURTO)
    assert relatorio.provedor == "heuristico"
    assert repositorio.execucoes[0].usou_reserva


async def test_resultado_da_reserva_nao_vai_para_o_cache() -> None:
    principal = ExtratorFixo(
        "groq",
        [ErroProvedor("groq", "429", temporario=True, espera=99), [fatos(1), fatos(2), fatos(3)]],
    )
    reserva = ExtratorFixo("heuristico", construir=caucao_cinco_meses)
    servico, _ = _servico(principal, reserva)

    primeiro = await servico.analisar(CONTRATO_CURTO)
    segundo = await servico.analisar(CONTRATO_CURTO)

    assert primeiro.provedor == "heuristico"
    assert segundo.provedor == "groq"  # o principal voltou e a análise foi refeita
    assert not segundo.em_cache


@pytest.mark.parametrize(
    ("texto", "mensagem"),
    [
        ("   ", "Cole o texto"),
        ("x" * 5_001, "limite é 5.000"),
        ("Um texto qualquer que não é contrato.", "Não encontrei cláusulas"),
    ],
)
async def test_entradas_invalidas_sao_recusadas_e_medidas(texto: str, mensagem: str) -> None:
    servico, repositorio = _servico(ExtratorFixo(construir=caucao_cinco_meses))
    with pytest.raises(EntradaInvalida, match=mensagem):
        await servico.analisar(texto)
    assert repositorio.execucoes[0].status == "entrada_invalida"


async def test_contrato_com_clausulas_demais() -> None:
    servico, _ = _servico(ExtratorFixo(construir=caucao_cinco_meses), max_clausulas=2)
    with pytest.raises(EntradaInvalida, match="3 cláusulas"):
        await servico.analisar(CONTRATO_CURTO)


async def test_sem_provedores_disponiveis() -> None:
    servico, repositorio = _servico(
        ExtratorFixo("a", [ErroProvedor("a", "fora", temporario=False)])
    )
    with pytest.raises(ProvedoresIndisponiveis):
        await servico.analisar(CONTRATO_CURTO)
    assert repositorio.execucoes[0].status == "provedores_indisponiveis"

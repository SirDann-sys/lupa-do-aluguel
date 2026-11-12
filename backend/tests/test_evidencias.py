import pytest

from app.dominio.evidencias import normalizar, trecho_presente, validar
from app.dominio.modelos import Campo, TipoGarantia
from tests.conftest import fatos, prova

CLAUSULA = (
    "O LOCATÁRIO prestará caução em dinheiro equivalente a 5 (cinco) aluguéis, "
    "depositada em conta poupança vinculada ao contrato."
)


def test_normalizar_ignora_caixa_espacos_e_aspas() -> None:
    assert normalizar("  “Taxa  de\nGestão”. ") == "taxa de gestao"


@pytest.mark.parametrize(
    "trecho",
    [
        "caução em dinheiro equivalente a 5 (cinco) aluguéis",
        "CAUÇÃO EM DINHEIRO   equivalente a 5 (cinco) aluguéis",
        "prestará caução em dinheiro ... depositada em conta poupança",
        "prestará caução em dinheiro … depositada em conta poupança",
        "caucao em dinheiro equivalente a 5 (cinco) alugueis",  # modelo que tira acentos
    ],
)
def test_trechos_aceitos(trecho: str) -> None:
    assert trecho_presente(trecho, CLAUSULA)


@pytest.mark.parametrize(
    "trecho",
    [
        "caução equivalente a 8 (oito) aluguéis acrescida de fiador solidário",
        "o locatário pagará taxa de administração",
        "curto",
        "",
    ],
)
def test_trechos_recusados(trecho: str) -> None:
    assert not trecho_presente(trecho, CLAUSULA)


def test_fato_com_prova_e_mantido() -> None:
    bruto = fatos(
        1,
        caucao_meses=5,
        garantias=[TipoGarantia.CAUCAO],
        evidencias=[
            prova(Campo.CAUCAO, "equivalente a 5 (cinco) aluguéis"),
            prova(Campo.GARANTIAS, "prestará caução em dinheiro"),
        ],
    )
    limpo, descartados = validar(bruto, CLAUSULA)
    assert descartados == []
    assert limpo.caucao_meses == 5
    assert limpo.garantias == [TipoGarantia.CAUCAO]


def test_fato_sem_prova_e_zerado() -> None:
    bruto = fatos(
        1,
        caucao_meses=5,
        inquilino_paga_taxa_imobiliaria=True,
        evidencias=[
            prova(Campo.CAUCAO, "equivalente a 5 (cinco) aluguéis"),
            prova(Campo.TAXA_IMOBILIARIA, "o locatário pagará taxa de administração"),
        ],
    )
    limpo, descartados = validar(bruto, CLAUSULA)
    assert descartados == [Campo.TAXA_IMOBILIARIA]
    assert limpo.inquilino_paga_taxa_imobiliaria is False
    assert limpo.caucao_meses == 5
    assert [e.campo for e in limpo.evidencias] == [Campo.CAUCAO]


def test_fato_sem_nenhuma_evidencia_e_zerado() -> None:
    limpo, descartados = validar(fatos(1, reajuste_periodicidade_meses=6), CLAUSULA)
    assert descartados == [Campo.REAJUSTE]
    assert limpo.reajuste_periodicidade_meses is None


def test_campo_nao_afirmado_nao_conta_como_descarte() -> None:
    _, descartados = validar(fatos(1), CLAUSULA)
    assert descartados == []

import pytest

from app.dominio.modelos import Campo, TipoGarantia
from app.dominio.regras import REGRAS, avaliar, em_meses, formatar_meses
from tests.conftest import fatos, prova


def regras_de(*lista: object) -> list[int]:
    return [a.regra for a in avaliar(list(lista))]  # type: ignore[arg-type]


def test_sete_regras_com_ids_sequenciais() -> None:
    assert [r.id for r in REGRAS] == [1, 2, 3, 4, 5, 6, 7]


def test_contrato_sem_fatos_nao_tem_achados() -> None:
    assert regras_de(fatos(1), fatos(2)) == []


@pytest.mark.parametrize(("meses", "viola"), [(2, False), (3, False), (3.01, True), (6, True)])
def test_regra_1_limite_de_tres_meses(meses: float, viola: bool) -> None:
    assert (1 in regras_de(fatos(1, caucao_meses=meses))) is viola


def test_regra_1_converte_valor_em_reais_pelo_aluguel_de_outra_clausula() -> None:
    contrato = [fatos(1, aluguel_mensal=2000), fatos(2, caucao_valor=8400)]
    [achado] = avaliar(contrato)
    assert achado.regra == 1
    assert achado.clausulas == [2]
    assert "4,2 meses" in achado.explicacao


def test_regra_1_valor_sem_aluguel_conhecido_nao_e_julgado() -> None:
    assert regras_de(fatos(1, caucao_valor=50_000)) == []


def test_regra_2_garantias_em_clausulas_diferentes() -> None:
    contrato = [
        fatos(1, garantias=[TipoGarantia.CAUCAO], evidencias=[prova(Campo.GARANTIAS, "caução")]),
        fatos(2),
        fatos(
            3,
            garantias=[TipoGarantia.SEGURO_FIANCA],
            evidencias=[prova(Campo.GARANTIAS, "seguro-fiança")],
        ),
    ]
    [achado] = avaliar(contrato)
    assert achado.regra == 2
    assert achado.clausulas == [1, 3]
    assert achado.trechos == ["caução", "seguro-fiança"]
    assert "caução e seguro-fiança" in achado.explicacao


def test_regra_2_mesma_garantia_repetida_nao_viola() -> None:
    contrato = [
        fatos(1, garantias=[TipoGarantia.FIADOR]),
        fatos(2, garantias=[TipoGarantia.FIADOR]),
    ]
    assert regras_de(*contrato) == []


@pytest.mark.parametrize(
    ("campo", "regra"),
    [
        ("inquilino_paga_despesas_extraordinarias", 3),
        ("inquilino_paga_taxa_imobiliaria", 4),
        ("pintura_obrigatoria_incondicional", 5),
    ],
)
def test_regras_booleanas(campo: str, regra: int) -> None:
    assert regras_de(fatos(1, **{campo: True})) == [regra]
    assert regras_de(fatos(1, **{campo: False})) == []


@pytest.mark.parametrize(
    ("periodo", "viola"), [(1, True), (6, True), (11, True), (12, False), (24, False), (0, False)]
)
def test_regra_6_periodicidade_minima(periodo: int, viola: bool) -> None:
    assert (6 in regras_de(fatos(1, reajuste_periodicidade_meses=periodo))) is viola


@pytest.mark.parametrize(("meses", "viola"), [(1, False), (2, True), (6, True)])
def test_regra_7_antecipacao(meses: float, viola: bool) -> None:
    assert (7 in regras_de(fatos(1, aluguel_antecipado_meses=meses))) is viola


def test_regra_7_por_valor() -> None:
    contrato = [fatos(1, aluguel_mensal=1000), fatos(2, aluguel_antecipado_valor=3000)]
    assert regras_de(*contrato) == [7]


def test_achados_saem_na_ordem_das_regras() -> None:
    contrato = [
        fatos(1, reajuste_periodicidade_meses=6),
        fatos(2, caucao_meses=4),
        fatos(3, pintura_obrigatoria_incondicional=True),
    ]
    assert regras_de(*contrato) == [1, 5, 6]


def test_em_meses_prefere_o_valor_declarado_em_meses() -> None:
    assert em_meses(2, 9999, 1000) == 2
    assert em_meses(None, 3000, 1000) == 3
    assert em_meses(None, None, 1000) is None


@pytest.mark.parametrize(("meses", "texto"), [(1, "1 mês"), (3, "3 meses"), (4.25, "4,2 meses")])
def test_formatar_meses(meses: float, texto: str) -> None:
    assert formatar_meses(meses) == texto

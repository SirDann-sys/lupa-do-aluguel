"""As 7 regras da Lei do Inquilinato, como dados + funções puras.

Cada regra recebe os fatos de TODAS as cláusulas (algumas regras só fazem
sentido no contrato inteiro: a garantia cumulada pode estar em duas cláusulas
diferentes, e a caução em reais precisa do aluguel, que fica em outra) e
devolve zero ou mais `Achado`. Nada aqui chama IA: dado o mesmo conjunto de
fatos, a resposta é sempre a mesma.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.dominio.modelos import Achado, Campo, FatosClausula, TipoGarantia

LIMITE_CAUCAO_MESES = 3
LIMITE_ANTECIPACAO_MESES = 1
PERIODICIDADE_MINIMA_REAJUSTE = 12

NOMES_GARANTIA = {
    TipoGarantia.CAUCAO: "caução",
    TipoGarantia.FIADOR: "fiador",
    TipoGarantia.SEGURO_FIANCA: "seguro-fiança",
    TipoGarantia.CESSAO_QUOTAS: "cessão de quotas de fundo de investimento",
}


@dataclass(frozen=True)
class Regra:
    id: int
    titulo: str
    artigo: str
    descricao: str
    orientacao: str


REGRAS: tuple[Regra, ...] = (
    Regra(
        1,
        "Caução acima de 3 meses de aluguel",
        "Lei 8.245/91, art. 38, §2º",
        "A caução em dinheiro não pode passar do equivalente a 3 meses de aluguel.",
        "Peça a redução da caução para no máximo 3 aluguéis.",
    ),
    Regra(
        2,
        "Mais de uma garantia ao mesmo tempo",
        "Lei 8.245/91, art. 37, parágrafo único",
        "O contrato só pode exigir uma modalidade de garantia: caução, fiador, "
        "seguro-fiança ou cessão de quotas.",
        "Escolha uma única garantia e peça a retirada das demais.",
    ),
    Regra(
        3,
        "Despesas extraordinárias de condomínio cobradas do inquilino",
        "Lei 8.245/91, art. 22, X",
        "Obras estruturais, reformas, fachada, equipamentos de segurança ou lazer e "
        "fundo de reserva são despesas do proprietário.",
        "Peça que a cláusula limite a cobrança às despesas ordinárias.",
    ),
    Regra(
        4,
        "Taxa de administração ou intermediação cobrada do inquilino",
        "Lei 8.245/91, art. 22, VII",
        "Comissão, taxa de administração ou de elaboração do contrato devidas à "
        "imobiliária são obrigação do proprietário.",
        "Peça a retirada da taxa ou que ela passe a ser paga pelo proprietário.",
    ),
    Regra(
        5,
        "Pintura nova obrigatória, mesmo sem necessidade",
        "Lei 8.245/91, art. 23, III",
        "O inquilino devolve o imóvel no estado em que recebeu, salvo o desgaste "
        "natural. Exigir pintura nova sem olhar o estado do imóvel é abusivo.",
        "Peça que a pintura dependa da vistoria de saída.",
    ),
    Regra(
        6,
        "Reajuste em prazo menor que 12 meses",
        "Lei 10.192/01, art. 2º, §1º",
        "O aluguel só pode ser reajustado depois de pelo menos 12 meses.",
        "Peça reajuste anual por um índice oficial (IPCA ou IGP-M).",
    ),
    Regra(
        7,
        "Cobrança antecipada de vários meses de aluguel",
        "Lei 8.245/91, art. 20 e art. 38, §2º",
        "Fora da locação para temporada, o proprietário não pode exigir aluguel "
        "antecipado. Cobrar vários meses de uma vez funciona como caução disfarçada.",
        "Peça que o pagamento seja mês a mês.",
    ),
)

REGRAS_POR_ID = {r.id: r for r in REGRAS}


def _achado(
    regra_id: int, explicacao: str, clausulas: Iterable[FatosClausula], campo: Campo
) -> Achado:
    regra = REGRAS_POR_ID[regra_id]
    lista = sorted(clausulas, key=lambda f: f.indice)
    trechos = [e.trecho for f in lista for e in f.evidencias if e.campo == campo]
    return Achado(
        regra=regra.id,
        titulo=regra.titulo,
        artigo=regra.artigo,
        explicacao=explicacao,
        orientacao=regra.orientacao,
        clausulas=[f.indice for f in lista],
        trechos=trechos,
    )


def aluguel_do_contrato(fatos: list[FatosClausula]) -> float | None:
    """O primeiro valor de aluguel mensal declarado no contrato."""
    return next((f.aluguel_mensal for f in fatos if f.aluguel_mensal), None)


def em_meses(meses: float | None, valor: float | None, aluguel: float | None) -> float | None:
    """Usa os meses declarados; se o contrato só dá reais, converte pelo aluguel."""
    if meses is not None:
        return meses
    if valor is not None and aluguel:
        return round(valor / aluguel, 2)
    return None


def formatar_meses(meses: float) -> str:
    texto = f"{meses:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texto} {'mês' if meses == 1 else 'meses'}"


def regra_1_caucao(fatos: list[FatosClausula]) -> list[Achado]:
    aluguel = aluguel_do_contrato(fatos)
    achados = []
    for f in fatos:
        meses = em_meses(f.caucao_meses, f.caucao_valor, aluguel)
        if meses is not None and meses > LIMITE_CAUCAO_MESES:
            explicacao = f"A caução equivale a {formatar_meses(meses)} de aluguel; o limite é 3."
            achados.append(_achado(1, explicacao, [f], Campo.CAUCAO))
    return achados


def regra_2_garantia_cumulada(fatos: list[FatosClausula]) -> list[Achado]:
    com_garantia = [f for f in fatos if f.garantias]
    tipos = {g for f in com_garantia for g in f.garantias}
    if len(tipos) <= 1:
        return []
    nomes = " e ".join(sorted(NOMES_GARANTIA[t] for t in tipos))
    explicacao = f"O contrato exige ao mesmo tempo {nomes}."
    return [_achado(2, explicacao, com_garantia, Campo.GARANTIAS)]


def regra_3_despesas_extraordinarias(fatos: list[FatosClausula]) -> list[Achado]:
    explicacao = "A cláusula passa ao inquilino despesas extraordinárias de condomínio."
    return [
        _achado(3, explicacao, [f], Campo.DESPESAS_EXTRAORDINARIAS)
        for f in fatos
        if f.inquilino_paga_despesas_extraordinarias
    ]


def regra_4_taxa_imobiliaria(fatos: list[FatosClausula]) -> list[Achado]:
    explicacao = "A cláusula cobra do inquilino uma taxa devida à imobiliária."
    return [
        _achado(4, explicacao, [f], Campo.TAXA_IMOBILIARIA)
        for f in fatos
        if f.inquilino_paga_taxa_imobiliaria
    ]


def regra_5_pintura(fatos: list[FatosClausula]) -> list[Achado]:
    explicacao = "A cláusula exige pintura nova independentemente do estado do imóvel."
    return [
        _achado(5, explicacao, [f], Campo.PINTURA_INCONDICIONAL)
        for f in fatos
        if f.pintura_obrigatoria_incondicional
    ]


def regra_6_reajuste(fatos: list[FatosClausula]) -> list[Achado]:
    achados = []
    for f in fatos:
        periodo = f.reajuste_periodicidade_meses
        if periodo is not None and 0 < periodo < PERIODICIDADE_MINIMA_REAJUSTE:
            explicacao = f"O reajuste ocorre a cada {formatar_meses(periodo)}; o mínimo é 12."
            achados.append(_achado(6, explicacao, [f], Campo.REAJUSTE))
    return achados


def regra_7_antecipacao(fatos: list[FatosClausula]) -> list[Achado]:
    aluguel = aluguel_do_contrato(fatos)
    achados = []
    for f in fatos:
        meses = em_meses(f.aluguel_antecipado_meses, f.aluguel_antecipado_valor, aluguel)
        if meses is not None and meses > LIMITE_ANTECIPACAO_MESES:
            explicacao = f"O contrato cobra {formatar_meses(meses)} de aluguel antecipado."
            achados.append(_achado(7, explicacao, [f], Campo.ALUGUEL_ANTECIPADO))
    return achados


AVALIADORES: tuple[Callable[[list[FatosClausula]], list[Achado]], ...] = (
    regra_1_caucao,
    regra_2_garantia_cumulada,
    regra_3_despesas_extraordinarias,
    regra_4_taxa_imobiliaria,
    regra_5_pintura,
    regra_6_reajuste,
    regra_7_antecipacao,
)


def avaliar(fatos: list[FatosClausula]) -> list[Achado]:
    """Aplica as 7 regras ao contrato inteiro, na ordem das regras."""
    return [achado for avaliador in AVALIADORES for achado in avaliador(fatos)]

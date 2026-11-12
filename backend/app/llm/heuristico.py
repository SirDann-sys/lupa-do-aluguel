"""Extrator por expressões regulares, sem rede e sem custo.

Serve a dois propósitos:
1. último elo da cadeia: se os provedores de IA estiverem fora, a análise
   ainda sai (com a precisão menor avisada no relatório);
2. linha de base da avaliação: mostra quanto a IA acrescenta de verdade.

Trabalha frase a frase, e a frase inteira vira a evidência, então a barreira
anti-alucinação sempre aceita o que ele afirma.
"""

import re

from app.dominio.modelos import Campo, Evidencia, FatosClausula, TipoGarantia
from app.llm.base import Extracao

_I = re.IGNORECASE

_EXTENSO = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "três": 3,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "doze": 12,
}
_QTD = r"(\d+(?:,\d+)?|" + "|".join(_EXTENSO) + r")"
_MESES = re.compile(
    _QTD + r"\s*(?:\([^)]*\)\s*)?(?:primeiros\s+|[úu]ltimos\s+)?"
    r"(?:meses|m[eê]s|alugu[eé]is|alugueres|aluguel)",
    _I,
)
_REAIS = re.compile(r"R\$\s*([\d.]+(?:,\d{1,2})?)")
_FRASES = re.compile(r"(?<=[.;])\s+")

_CAUCAO = re.compile(
    r"cau[çc][ãa]o|reforço de garantia|conta vinculada|garantia.{0,80}dep[óo]sit|"
    r"dep[óo]sit.{0,80}garantia",
    _I,
)
_FIADOR = re.compile(r"\bfiador", _I)
_SEGURO_FIANCA = re.compile(r"seguro[\s-]*fian[çc]a", _I)
_NEGACAO_GARANTIA = re.compile(r"n[ãa]o (?:sendo|ser[áa]) exigid|nenhuma outra", _I)
_ANTECIPADO = re.compile(r"antecipad|adiantamento", _I)
_NAO_ANTECIPACAO = re.compile(r"rescis|devolu[çc][ãa]o antecipada|t[ée]rmino antecipado", _I)
_ALUGUEL = re.compile(r"aluguel mensal|valor mensal do aluguel|valor do aluguel", _I)
_REAJUSTE = re.compile(r"reajust|atualiza|corrigid|correção", _I)
_A_CADA = re.compile(r"a cada " + _QTD + r"\s*(?:\([^)]*\)\s*)?meses", _I)
_PERIODOS = (
    (re.compile(r"mensalmente|reajuste mensal", _I), 1),
    (re.compile(r"bimestral", _I), 2),
    (re.compile(r"trimestral", _I), 3),
    (re.compile(r"semestral", _I), 6),
    (re.compile(r"bienal", _I), 24),
    (re.compile(r"anual", _I), 12),
)
_EXTRAORDINARIAS = re.compile(
    r"extraordin|fundo de (?:reserva|obras)|obras? estrutur|reformas? estrutur|fachada", _I
)
_TAXA = re.compile(
    r"taxa de (?:administra|intermedia|gest|elabora|agenciamento|contrato)|comiss[ãa]o|"
    r"intermedia[çc][ãa]o",
    _I,
)
_PINTURA = re.compile(r"pintur|pintad", _I)
_INCONDICIONAL = re.compile(r"independ", _I)
_LOCATARIO = re.compile(r"locat[áa]rio|inquilino", _I)
_LOCADOR = re.compile(r"locador|propriet[áa]rio", _I)


def _numero(texto: str) -> float:
    texto = texto.lower()
    return float(_EXTENSO.get(texto, 0)) or float(texto.replace(",", "."))


def _reais(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def _meses(frase: str) -> float | None:
    m = _MESES.search(frase)
    return _numero(m.group(1)) if m else None


def _valor(frase: str) -> float | None:
    m = _REAIS.search(frase)
    return _reais(m.group(1)) if m else None


def _cobra_do_inquilino(frase: str) -> bool:
    return bool(_LOCATARIO.search(frase)) and not _LOCADOR.search(frase)


def _periodicidade(frase: str) -> int | None:
    if m := _A_CADA.search(frase):
        return int(_numero(m.group(1)))
    return next((meses for padrao, meses in _PERIODOS if padrao.search(frase)), None)


def extrair_clausula(indice: int, clausula: str) -> FatosClausula:
    dados: dict[str, object] = {}
    garantias: set[TipoGarantia] = set()
    evidencias: list[Evidencia] = []

    def prova(campo: Campo, frase: str) -> None:
        if not any(e.campo == campo for e in evidencias):
            evidencias.append(Evidencia(campo=campo, trecho=frase))

    for frase in _FRASES.split(clausula):
        antecipacao = bool(_ANTECIPADO.search(frase)) and not _NAO_ANTECIPACAO.search(frase)

        if antecipacao:
            meses, valor = _meses(frase), _valor(frase)
            if meses or valor:
                dados["aluguel_antecipado_meses"] = meses
                dados["aluguel_antecipado_valor"] = valor
                prova(Campo.ALUGUEL_ANTECIPADO, frase)
        elif _CAUCAO.search(frase) and not _NEGACAO_GARANTIA.search(frase):
            garantias.add(TipoGarantia.CAUCAO)
            prova(Campo.GARANTIAS, frase)
            meses, valor = _meses(frase), _valor(frase)
            if meses or valor:
                dados["caucao_meses"] = meses
                dados["caucao_valor"] = valor
                prova(Campo.CAUCAO, frase)
        elif _ALUGUEL.search(frase) and (valor := _valor(frase)):
            dados["aluguel_mensal"] = valor
            prova(Campo.ALUGUEL_MENSAL, frase)

        if _FIADOR.search(frase):
            garantias.add(TipoGarantia.FIADOR)
            prova(Campo.GARANTIAS, frase)
        if _SEGURO_FIANCA.search(frase):
            garantias.add(TipoGarantia.SEGURO_FIANCA)
            prova(Campo.GARANTIAS, frase)

        if _REAJUSTE.search(frase) and (periodo := _periodicidade(frase)):
            dados["reajuste_periodicidade_meses"] = periodo
            prova(Campo.REAJUSTE, frase)
        if _EXTRAORDINARIAS.search(frase) and _cobra_do_inquilino(frase):
            dados["inquilino_paga_despesas_extraordinarias"] = True
            prova(Campo.DESPESAS_EXTRAORDINARIAS, frase)
        if _TAXA.search(frase) and _cobra_do_inquilino(frase):
            dados["inquilino_paga_taxa_imobiliaria"] = True
            prova(Campo.TAXA_IMOBILIARIA, frase)
        if _PINTURA.search(frase) and _INCONDICIONAL.search(frase):
            dados["pintura_obrigatoria_incondicional"] = True
            prova(Campo.PINTURA_INCONDICIONAL, frase)

    return FatosClausula.model_validate(
        {"indice": indice, "garantias": sorted(garantias), "evidencias": evidencias, **dados}
    )


class ExtratorHeuristico:
    nome = "heuristico"
    modelo = "regex-v1"

    async def extrair(self, clausulas: list[str]) -> Extracao:
        fatos = [extrair_clausula(i, c) for i, c in enumerate(clausulas, start=1)]
        return Extracao(fatos=fatos, provedor=self.nome, modelo=self.modelo)

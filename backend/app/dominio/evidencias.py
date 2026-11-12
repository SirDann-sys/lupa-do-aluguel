"""Barreira contra alucinação: todo fato afirmado precisa de prova no texto.

O extrator devolve, junto de cada fato, o trecho da cláusula que o sustenta.
Aqui o trecho é procurado na cláusula original. Se não estiver lá, o fato é
zerado antes de chegar às regras, e o descarte é contado no relatório.

A comparação tolera o que um modelo costuma mudar sem mudar o sentido:
caixa, acentos, espaços, aspas tipográficas e reticências marcando um corte.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.dominio.modelos import Campo, FatosClausula

COBERTURA_MINIMA = 0.85
TAMANHO_MINIMO_PEDACO = 8

_TROCAS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})
_ESPACOS = re.compile(r"\s+")
_RETICENCIAS = re.compile(r"\.{3,}|…|\[\.\.\.\]")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, aspas e traços padronizados, espaços colapsados."""
    texto = unicodedata.normalize("NFKD", texto.translate(_TROCAS).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", texto).strip(" \"'.,;:")


def _pedaco_presente(pedaco: str, clausula: str) -> bool:
    if pedaco in clausula:
        return True
    casamento = SequenceMatcher(None, pedaco, clausula, autojunk=False).find_longest_match()
    return casamento.size >= COBERTURA_MINIMA * len(pedaco)


def trecho_presente(trecho: str, clausula: str) -> bool:
    """True se o trecho (ou cada parte dele, quando cortado por reticências) está na cláusula."""
    alvo = normalizar(clausula)
    pedacos = [normalizar(p) for p in _RETICENCIAS.split(trecho)]
    pedacos = [p for p in pedacos if len(p) >= TAMANHO_MINIMO_PEDACO]
    return bool(pedacos) and all(_pedaco_presente(p, alvo) for p in pedacos)


@dataclass(frozen=True)
class _Fato:
    afirmado: Callable[[FatosClausula], bool]
    zerar: dict[str, object]


_FATOS: dict[Campo, _Fato] = {
    Campo.GARANTIAS: _Fato(lambda f: bool(f.garantias), {"garantias": []}),
    Campo.CAUCAO: _Fato(
        lambda f: f.caucao_meses is not None or f.caucao_valor is not None,
        {"caucao_meses": None, "caucao_valor": None},
    ),
    Campo.ALUGUEL_MENSAL: _Fato(lambda f: f.aluguel_mensal is not None, {"aluguel_mensal": None}),
    Campo.ALUGUEL_ANTECIPADO: _Fato(
        lambda f: f.aluguel_antecipado_meses is not None or f.aluguel_antecipado_valor is not None,
        {"aluguel_antecipado_meses": None, "aluguel_antecipado_valor": None},
    ),
    Campo.REAJUSTE: _Fato(
        lambda f: f.reajuste_periodicidade_meses is not None,
        {"reajuste_periodicidade_meses": None},
    ),
    Campo.DESPESAS_EXTRAORDINARIAS: _Fato(
        lambda f: f.inquilino_paga_despesas_extraordinarias,
        {"inquilino_paga_despesas_extraordinarias": False},
    ),
    Campo.TAXA_IMOBILIARIA: _Fato(
        lambda f: f.inquilino_paga_taxa_imobiliaria, {"inquilino_paga_taxa_imobiliaria": False}
    ),
    Campo.PINTURA_INCONDICIONAL: _Fato(
        lambda f: f.pintura_obrigatoria_incondicional,
        {"pintura_obrigatoria_incondicional": False},
    ),
}


def validar(fatos: FatosClausula, clausula: str) -> tuple[FatosClausula, list[Campo]]:
    """Devolve os fatos com prova no texto e a lista de campos descartados."""
    evidencias = [e for e in fatos.evidencias if trecho_presente(e.trecho, clausula)]
    provados = {e.campo for e in evidencias}

    zerar: dict[str, object] = {}
    descartados: list[Campo] = []
    for campo, fato in _FATOS.items():
        if fato.afirmado(fatos) and campo not in provados:
            zerar.update(fato.zerar)
            descartados.append(campo)

    limpo = fatos.model_copy(update={**zerar, "evidencias": evidencias})
    return limpo, descartados

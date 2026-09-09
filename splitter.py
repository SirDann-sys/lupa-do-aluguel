"""Split simples de um contrato em cláusulas candidatas.

Sem parser jurídico, conforme a Fase 1 pede: quebra por parágrafo (linha em
branco) e, dentro de blocos com múltiplos itens, por marcadores de
numeração no início da linha. A precisão fina da classificação fica a
cargo do LLM, não deste split.
"""

import re

MIN_TAMANHO = 40

_MARCADOR = re.compile(
    r"""(?imx)
    ^\s*(?:
        CL[ÁA]USULA \s+ \S+                    # CLÁUSULA PRIMEIRA / CLÁUSULA 1ª
        | PAR[ÁA]GRAFO \s+ (?:[ÚU]NICO|PRIMEIRO|SEGUNDO|TERCEIRO|QUARTO|QUINTO|\d+º?)
        | §\s*\d+º?
        | (?=\d+\.) \d+(?:\.\d+)*\.?\s+\S       # "1." / "1.1" seguido de texto
                                                 # (lookahead exige um ponto logo
                                                 # após os dígitos, senão "12 meses"
                                                 # no meio de uma frase seria
                                                 # confundido com marcador)
        | [a-z]\)
    )
    """
)


def split_clausulas(texto: str) -> list[str]:
    """Divide o texto de um contrato em uma lista de cláusulas candidatas."""
    blocos = [b.strip() for b in re.split(r"\n\s*\n", texto.strip()) if b.strip()]

    marcadores_por_bloco = [
        [m.start() for m in _MARCADOR.finditer(bloco)] for bloco in blocos
    ]
    documento_usa_marcadores = any(marcadores_por_bloco)

    clausulas: list[str] = []
    for bloco, pontos in zip(blocos, marcadores_por_bloco):
        if not pontos:
            # Bloco sem nenhum marcador de numeração. Se o resto do
            # documento usa marcadores (CLÁUSULA X, §N, "1.", ...), este
            # bloco é texto de contorno — preâmbulo, identificação das
            # partes, fechamento/assinatura — não uma cláusula real.
            if documento_usa_marcadores:
                continue
            fragmentos = [bloco]
        else:
            limites = pontos + [len(bloco)]
            fragmentos = [
                bloco[inicio:fim].strip()
                for inicio, fim in zip(limites, limites[1:])
            ]

        for fragmento in fragmentos:
            fragmento = fragmento.strip()
            if len(fragmento) >= MIN_TAMANHO:
                clausulas.append(fragmento)

    return clausulas

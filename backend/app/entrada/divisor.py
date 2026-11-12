"""Divide o texto de um contrato em cláusulas.

Sem parser jurídico: quebra por parágrafo (linha em branco) e, dentro de um
bloco, pelos marcadores de numeração no início da linha ("CLÁUSULA QUINTA",
"Cláusula 5ª", "§ 2º", "5.1", "a)"). Quando o documento usa marcadores, os
blocos sem marcador (preâmbulo, qualificação das partes, local e data) são
descartados: não são cláusulas e só gastariam tokens.
"""

import itertools
import re

TAMANHO_MINIMO = 40

_MARCADOR = re.compile(
    r"""(?imx)
    ^\s*(?:
        CL[ÁA]USULA \s+ \S+                        # CLÁUSULA PRIMEIRA / Cláusula 1ª
        | PAR[ÁA]GRAFO \s+ (?:[ÚU]NICO|PRIMEIRO|SEGUNDO|TERCEIRO|QUARTO|QUINTO|\d+º?)
        | §\s*\d+º?
        | (?=\d+\.) \d+(?:\.\d+)*\.?\s+\S           # "1." ou "1.1" seguido de texto; o
                                                     # lookahead exige o ponto, senão
                                                     # "12 meses" no começo da linha viraria
                                                     # marcador
        | [a-z]\)
    )
    """
)


def dividir(texto: str) -> list[str]:
    """Lista de cláusulas candidatas, na ordem do documento."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocos = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]

    marcadores = [[m.start() for m in _MARCADOR.finditer(b)] for b in blocos]
    usa_marcadores = any(marcadores)

    clausulas: list[str] = []
    for bloco, pontos in zip(blocos, marcadores, strict=True):
        if not pontos:
            if usa_marcadores:
                continue
            fragmentos = [bloco]
        else:
            # O que vem antes do primeiro marcador do bloco (ex.: o título do
            # contrato colado junto) não é cláusula e fica de fora.
            limites = [*pontos, len(bloco)]
            fragmentos = [bloco[i:f] for i, f in itertools.pairwise(limites)]

        clausulas.extend(
            " ".join(f.split()) for f in fragmentos if len(f.strip()) >= TAMANHO_MINIMO
        )

    return clausulas

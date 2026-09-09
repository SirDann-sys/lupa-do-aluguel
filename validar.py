"""Runner do critério de conclusão da Fase 1.

Para cada contrato listado em contratos/gabarito.json: faz o split, chama
o analyzer, e compara o conjunto de regras detectadas contra o esperado.
Imprime um relatório por arquivo e termina com exit code 0 (passou) ou 1
(falhou) — este script, não a UI, decide se a Fase 1 está concluída.
"""

import json
import sys
from pathlib import Path

from analyzer import analisar
from splitter import split_clausulas

CONTRATOS_DIR = Path(__file__).parent / "contratos"
GABARITO_PATH = CONTRATOS_DIR / "gabarito.json"


def validar_contrato(nome_arquivo: str, regras_esperadas: set[int]) -> bool:
    caminho = CONTRATOS_DIR / nome_arquivo
    texto = caminho.read_text(encoding="utf-8")

    clausulas = split_clausulas(texto)
    resultado = analisar(clausulas)

    regras_detectadas = {
        v["regra"]
        for item in resultado
        for v in item["violacoes"]
    }

    faltantes = regras_esperadas - regras_detectadas
    extras = regras_detectadas - regras_esperadas
    passou = not faltantes and not extras

    print(f"\n=== {nome_arquivo} ===")
    print(f"  Cláusulas extraídas: {len(clausulas)}")
    print(f"  Regras esperadas:    {sorted(regras_esperadas) or '(nenhuma)'}")
    print(f"  Regras detectadas:   {sorted(regras_detectadas) or '(nenhuma)'}")
    if faltantes:
        print(f"  FALTANTES (falso negativo): {sorted(faltantes)}")
    if extras:
        print(f"  EXTRAS (falso positivo):    {sorted(extras)}")
    print(f"  Resultado: {'PASSOU' if passou else 'FALHOU'}")

    return passou


def main() -> int:
    gabarito = json.loads(GABARITO_PATH.read_text(encoding="utf-8"))

    resultados = {
        nome: validar_contrato(nome, set(regras))
        for nome, regras in gabarito.items()
    }

    total = len(resultados)
    aprovados = sum(resultados.values())

    print(f"\n=== Veredito Fase 1: {aprovados}/{total} contratos passaram ===")

    return 0 if aprovados == total else 1


if __name__ == "__main__":
    sys.exit(main())

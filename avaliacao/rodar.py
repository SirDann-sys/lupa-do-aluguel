"""Avaliação ponta a ponta contra o gabarito.

Roda cada contrato de `avaliacao/contratos/` pelo mesmo serviço que a API usa
e compara as regras apontadas com `avaliacao/gabarito.json`. Mede precisão e
recall por regra, separando dois conjuntos:

- desenvolvimento: contratos usados para escrever o extrator heurístico;
- teste_cego: escritos depois, sem nenhum ajuste posterior da heurística.

    python avaliacao/rodar.py --provedor heuristico
    python avaliacao/rodar.py --provedor groq --pausa 20 --saida avaliacao/resultados/groq.json

Os números saem como forem: o objetivo é medir, não passar.
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent / "backend"))

import httpx  # noqa: E402

from app.config import Config  # noqa: E402
from app.db.repositorio import RepositorioNulo  # noqa: E402
from app.dominio.regras import REGRAS  # noqa: E402
from app.llm.base import Extrator  # noqa: E402
from app.llm.cadeia import Cadeia  # noqa: E402
from app.main import montar_extratores  # noqa: E402
from app.servicos.analise import ServicoAnalise  # noqa: E402
from app.servicos.cache import CacheTTL  # noqa: E402

CONJUNTOS = ("desenvolvimento", "teste_cego")


@dataclass
class Placar:
    vp: int = 0
    fp: int = 0
    fn: int = 0

    def contar(self, apontou: bool, esperado: bool) -> None:
        self.vp += apontou and esperado
        self.fp += apontou and not esperado
        self.fn += esperado and not apontou

    def __add__(self, outro: "Placar") -> "Placar":
        return Placar(self.vp + outro.vp, self.fp + outro.fp, self.fn + outro.fn)

    def resumo(self) -> dict[str, Any]:
        precisao = self.vp / (self.vp + self.fp) if self.vp + self.fp else None
        recall = self.vp / (self.vp + self.fn) if self.vp + self.fn else None
        return {
            "precisao": round(precisao, 3) if precisao is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "vp": self.vp,
            "fp": self.fp,
            "fn": self.fn,
        }


def carregar_gabarito() -> dict[str, dict[str, Any]]:
    bruto: dict[str, Any] = json.loads((RAIZ / "gabarito.json").read_text("utf-8"))
    return {k: v for k, v in bruto.items() if not k.startswith("_")}


def _escolher(provedor: str, extratores: list[Extrator]) -> list[Extrator]:
    if provedor == "cadeia":
        return extratores
    escolhidos = [e for e in extratores if e.nome == provedor]
    if not escolhidos:
        raise SystemExit(f"Provedor '{provedor}' indisponível (falta a chave LUPA_..._API_KEY?).")
    return escolhidos


async def avaliar(provedor: str, pausa: float) -> dict[str, Any]:
    gabarito = carregar_gabarito()
    placares: dict[str, dict[int, Placar]] = {c: defaultdict(Placar) for c in CONJUNTOS}
    detalhes: list[dict[str, Any]] = []
    modelo = ""

    async with httpx.AsyncClient() as cliente:
        extratores = _escolher(provedor, montar_extratores(Config(), cliente))
        servico = ServicoAnalise(
            Cadeia(extratores, tentativas=3, espera_maxima=60),
            RepositorioNulo(),
            CacheTTL(0, 1),
            max_caracteres=100_000,
            max_clausulas=200,
        )
        for i, (arquivo, item) in enumerate(sorted(gabarito.items())):
            if i and pausa:
                await asyncio.sleep(pausa)
            texto = (RAIZ / "contratos" / arquivo).read_text("utf-8")
            inicio = time.perf_counter()
            relatorio = await servico.analisar(texto)
            ms = round((time.perf_counter() - inicio) * 1000)
            modelo = relatorio.modelo

            apontadas = {a.regra for a in relatorio.achados}
            esperadas = set(item["regras"])
            for regra in REGRAS:
                placares[item["conjunto"]][regra.id].contar(
                    regra.id in apontadas, regra.id in esperadas
                )
            certo = apontadas == esperadas
            detalhes.append(
                {
                    "arquivo": arquivo,
                    "conjunto": item["conjunto"],
                    "esperadas": sorted(esperadas),
                    "apontadas": sorted(apontadas),
                    "certo": certo,
                    "provedor": relatorio.provedor,
                    "fatos_descartados": relatorio.fatos_descartados,
                    "ms": ms,
                }
            )
            print(
                f"[{'ok ' if certo else 'ERR'}] {arquivo:32} esperadas={sorted(esperadas)} "
                f"apontadas={sorted(apontadas)} ({relatorio.provedor}, {ms} ms)"
            )

    conjuntos = {}
    for nome in CONJUNTOS:
        do_conjunto = [d for d in detalhes if d["conjunto"] == nome]
        total = sum(placares[nome].values(), Placar())
        conjuntos[nome] = {
            "contratos": len(do_conjunto),
            "contratos_certos": sum(1 for d in do_conjunto if d["certo"]),
            **total.resumo(),
            "por_regra": {str(r.id): placares[nome][r.id].resumo() for r in REGRAS},
        }
    return {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "provedor": provedor,
        "modelo": modelo,
        "conjuntos": conjuntos,
        "detalhes": detalhes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Avaliação contra o gabarito.")
    parser.add_argument(
        "--provedor", default="heuristico", choices=["heuristico", "groq", "gemini", "cadeia"]
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=0.0,
        help="segundos entre contratos, para respeitar o limite grátis",
    )
    parser.add_argument("--saida", type=Path, help="grava o resultado em JSON neste arquivo")
    args = parser.parse_args()

    dados = asyncio.run(avaliar(args.provedor, args.pausa))
    print()
    for nome, c in dados["conjuntos"].items():
        print(
            f"{nome:16} {c['contratos_certos']}/{c['contratos']} contratos exatos · "
            f"precisão {c['precisao']} · recall {c['recall']}"
        )
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

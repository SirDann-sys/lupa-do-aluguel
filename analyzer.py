"""Classificação de cláusulas contra as 7 regras do TrapDoor.

Uma única chamada à API da Anthropic: o system prompt carrega as 7 regras
(fonte única em rules.py) e a saída é forçada via output_config/schema para
um formato estruturado — sem parse frágil de markdown.

Uma cláusula pode violar mais de uma regra ao mesmo tempo (ex.: caução
acima do limite E cumulada com fiador, na mesma cláusula de garantia) —
por isso `violacoes` é uma lista, não um campo único.
"""

import os

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

import rules

load_dotenv()

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = f"""\
Você é um analista jurídico especializado em contratos de locação \
residencial no Brasil, sob a Lei do Inquilinato (Lei 8.245/91).

Você recebe uma lista de cláusulas extraídas de um contrato. Para CADA \
cláusula, avalie se ela viola uma ou mais das 7 regras abaixo. Essas são \
as ÚNICAS regras que contam como violação nesta análise — não aponte \
nada que não se enquadre EXPLICITAMENTE em uma delas, mesmo que pareça \
desfavorável ao locatário por outros motivos.

REGRAS:
{rules.formatar_para_prompt()}

IMPORTANTE: uma mesma cláusula pode violar MAIS DE UMA regra ao mesmo \
tempo. Por exemplo, uma única cláusula de garantia pode exigir cumulação \
de fiador e caução (regra 2) E, na mesma frase, fixar essa caução acima \
do limite legal de 3 meses (regra 1) — as duas violações coexistem no \
mesmo trecho e ambas devem ser reportadas. Nunca pare de procurar depois \
de encontrar a primeira violação em uma cláusula — verifique a cláusula \
contra as 7 regras de forma independente, uma a uma.

Para cada cláusula, devolva um objeto com:
- clausula: o texto da cláusula (pode resumir se for muito longo, mas \
mantenha o trecho relevante literal)
- violacoes: uma lista com um item para CADA regra violada (vazia se a \
cláusula não violar nenhuma). Cada item tem:
  - regra: o número da regra violada (1 a 7)
  - artigo: a base legal daquela regra
  - explicacao: uma frase curta e objetiva explicando o porquê

Seja conservador: na dúvida, prefira não reportar violação. Cláusulas \
comuns e válidas (fiador único sem outra garantia cumulada, multa por \
rescisão antecipada, reajuste anual por índice oficial, obrigação de \
conservação do imóvel) NÃO são violações.
"""


class Violacao(BaseModel):
    regra: int = Field(ge=1, le=7)
    artigo: str
    explicacao: str


class ClausulaAnalisada(BaseModel):
    clausula: str
    violacoes: list[Violacao]


class Analise(BaseModel):
    clausulas: list[ClausulaAnalisada]


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não está definida (ou está vazia) no .env."
        )
    return anthropic.Anthropic(api_key=api_key)


def analisar(clausulas: list[str]) -> list[dict]:
    """Classifica cada cláusula contra as 7 regras. Retorna uma lista de dicts.

    Cada dict tem: clausula (str), classificacao ("abusiva"/"sem_alerta",
    derivada — não vem do modelo, para nunca divergir da lista abaixo) e
    violacoes (list[dict] com regra/artigo/explicacao, vazia se sem_alerta).
    """
    if not clausulas:
        return []

    client = _client()

    texto_clausulas = "\n\n".join(
        f"[{i}] {clausula}" for i, clausula in enumerate(clausulas, start=1)
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Analise cada uma das cláusulas numeradas abaixo, uma "
                    "por uma, e devolva um item de análise para cada "
                    "número — nenhuma cláusula pode ficar de fora.\n\n"
                    f"{texto_clausulas}"
                ),
            }
        ],
        output_format=Analise,
    )

    resultado = response.parsed_output.clausulas

    saida = []
    for item in resultado:
        violacoes = [v.model_dump() for v in item.violacoes]
        saida.append(
            {
                "clausula": item.clausula,
                "classificacao": "abusiva" if violacoes else "sem_alerta",
                "violacoes": violacoes,
            }
        )

    return saida

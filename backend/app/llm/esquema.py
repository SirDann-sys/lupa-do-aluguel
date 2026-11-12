"""Converte o JSON Schema do Pydantic para o modo estrito dos provedores.

O modo estrito (decodificação restrita) exige: todos os campos em `required`,
`additionalProperties: false` em todo objeto e nada de `$ref`. Opcional vira
`"type": [..., "null"]`. Assim o modelo não consegue gerar JSON fora do
formato; a validação Pydantic do outro lado continua como segunda barreira.
"""

from typing import Any

from pydantic import BaseModel

_CHAVES_DESCARTADAS = {"title", "default"}


def _nulo_como_tipo(no: dict[str, Any]) -> dict[str, Any]:
    """anyOf [X, null] -> X com type [tipo, "null"], quando X é um tipo simples."""
    opcoes = no.get("anyOf")
    if not isinstance(opcoes, list) or len(opcoes) != 2:
        return no
    nao_nulos = [o for o in opcoes if o.get("type") != "null"]
    if len(nao_nulos) != 1 or not isinstance(nao_nulos[0].get("type"), str):
        return no
    resto = {k: v for k, v in no.items() if k != "anyOf"}
    base = dict(nao_nulos[0])
    base["type"] = [base["type"], "null"]
    return {**base, **resto}


def esquema_estrito(
    modelo: type[BaseModel], *, additional_properties: bool = True
) -> dict[str, Any]:
    bruto = modelo.model_json_schema()
    definicoes: dict[str, Any] = bruto.pop("$defs", {})

    def resolver(no: Any) -> Any:
        if isinstance(no, list):
            return [resolver(item) for item in no]
        if not isinstance(no, dict):
            return no
        if "$ref" in no:
            return resolver(definicoes[no["$ref"].rsplit("/", 1)[-1]])
        novo = {k: resolver(v) for k, v in no.items() if k not in _CHAVES_DESCARTADAS}
        novo = _nulo_como_tipo(novo)
        if novo.get("type") == "object" and "properties" in novo:
            novo["required"] = list(novo["properties"])
            if additional_properties:
                novo["additionalProperties"] = False
        if not additional_properties:
            novo.pop("additionalProperties", None)
        return novo

    resultado: dict[str, Any] = resolver(bruto)
    return resultado

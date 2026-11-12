"""Adaptador para APIs no formato /chat/completions da OpenAI.

Groq e Gemini expõem esse formato, então um único cliente HTTP atende os dois.
Sem SDK: `httpx` direto, o que deixa a dependência pequena e o teste simples
(um `httpx.MockTransport` simula qualquer resposta).
"""

from typing import Any

import httpx
from pydantic import ValidationError

from app.dominio.modelos import RespostaExtracao
from app.llm.base import ErroProvedor, Extracao
from app.llm.esquema import esquema_estrito
from app.llm.prompt import SISTEMA, mensagem_usuario


class ProvedorOpenAICompat:
    def __init__(
        self,
        nome: str,
        url_base: str,
        modelo: str,
        chave: str,
        cliente: httpx.AsyncClient,
        *,
        estrito: bool = True,
        additional_properties: bool = True,
        timeout: float = 45.0,
        max_tokens: int = 8000,
    ) -> None:
        self.nome = nome
        self.modelo = modelo
        self._url = url_base.rstrip("/") + "/chat/completions"
        self._chave = chave
        self._cliente = cliente
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._formato = {
            "type": "json_schema",
            "json_schema": {
                "name": "fatos_clausulas",
                "strict": estrito,
                "schema": esquema_estrito(
                    RespostaExtracao, additional_properties=additional_properties
                ),
            },
        }

    def _corpo(self, clausulas: list[str]) -> dict[str, Any]:
        return {
            "model": self.modelo,
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": mensagem_usuario(clausulas)},
            ],
            "response_format": self._formato,
        }

    async def extrair(self, clausulas: list[str]) -> Extracao:
        try:
            resposta = await self._cliente.post(
                self._url,
                json=self._corpo(clausulas),
                headers={"Authorization": f"Bearer {self._chave}"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as erro:
            raise ErroProvedor(self.nome, "tempo esgotado", temporario=True) from erro
        except httpx.HTTPError as erro:
            raise ErroProvedor(
                self.nome, f"falha de rede ({type(erro).__name__})", temporario=True
            ) from erro

        self._checar_status(resposta)

        try:
            dados = resposta.json()
            conteudo = dados["choices"][0]["message"]["content"]
            resultado = RespostaExtracao.model_validate_json(conteudo)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as erro:
            # Formato inválido costuma ser acaso do modelo: vale outra tentativa.
            raise ErroProvedor(self.nome, "resposta fora do formato", temporario=True) from erro

        uso = dados.get("usage") or {}
        return Extracao(
            fatos=resultado.clausulas,
            provedor=self.nome,
            modelo=self.modelo,
            tokens_entrada=int(uso.get("prompt_tokens", 0)),
            tokens_saida=int(uso.get("completion_tokens", 0)),
        )

    def _checar_status(self, resposta: httpx.Response) -> None:
        status = resposta.status_code
        if status < 400:
            return
        if status == 429:
            espera = _segundos(resposta.headers.get("retry-after"))
            raise ErroProvedor(self.nome, "limite de uso atingido", temporario=True, espera=espera)
        if status >= 500:
            raise ErroProvedor(self.nome, f"erro do servidor ({status})", temporario=True)
        # 4xx: chave inválida, modelo inexistente, requisição recusada. Não adianta repetir.
        raise ErroProvedor(self.nome, f"requisição recusada ({status})", temporario=False)


def _segundos(valor: str | None) -> float | None:
    try:
        return float(valor) if valor is not None else None
    except ValueError:
        return None

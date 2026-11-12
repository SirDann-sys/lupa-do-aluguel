"""Mascara dados pessoais com formato reconhecível antes de qualquer envio à IA.

Nenhuma das 7 regras depende de CPF, RG, CNPJ, e-mail, telefone ou CEP, então
esses dados saem do texto logo na entrada: não vão para o provedor de IA, nem
para o cache, nem para a resposta. Valores em reais (R$ 2.000,00) e números de
cláusula ficam intactos.

Nomes próprios não têm formato detectável com segurança; para eles, a página
pede que o usuário apague antes de enviar.
"""

import re
from collections.abc import Callable

Substituto = str | Callable[[re.Match[str]], str]


def _manter_prefixo(rotulo: str) -> Callable[[re.Match[str]], str]:
    """Para padrões do tipo 'RG nº 12.345.678-9': mantém 'RG nº ' e troca só o número."""
    return lambda m: f"{m.group(1)}{rotulo}"


_PADROES: tuple[tuple[re.Pattern[str], Substituto], ...] = (
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[E-MAIL]"),
    (re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"), "[CNPJ]"),
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[CPF]"),
    (re.compile(r"(\bCPF\D{0,20}?)\d{11}\b", re.I), _manter_prefixo("[CPF]")),
    (re.compile(r"(\bRG\D{0,20}?)[\dXx][\dXx.\-/]{4,14}[\dXx]", re.I), _manter_prefixo("[RG]")),
    (re.compile(r"(?<!\d)(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}-\d{4}(?!\d)"), "[TELEFONE]"),
    (re.compile(r"\b\d{5}-\d{3}\b"), "[CEP]"),
)


def mascarar(texto: str) -> tuple[str, int]:
    """Devolve o texto mascarado e quantos dados pessoais foram substituídos."""
    total = 0
    for padrao, substituto in _PADROES:
        texto, n = padrao.subn(substituto, texto)
        total += n
    return texto, total

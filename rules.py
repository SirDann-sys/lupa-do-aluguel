"""As 7 regras da base de conhecimento v1 do TrapDoor.

Fonte única usada tanto pelo prompt do analyzer quanto pelo validar.py,
para que o texto injetado no modelo e o gabarito de teste nunca divirjam.
"""

REGRAS = [
    {
        "id": 1,
        "titulo": "Caução em dinheiro superior a 3 meses de aluguel",
        "artigo": "Art. 38, §2º",
        "descricao": (
            "A caução (garantia em dinheiro) exigida do locatário não pode "
            "ultrapassar o equivalente a 3 (três) meses de aluguel."
        ),
    },
    {
        "id": 2,
        "titulo": "Mais de uma garantia cumulada",
        "artigo": "Art. 37, parágrafo único",
        "descricao": (
            "É vedado exigir mais de uma modalidade de garantia no mesmo "
            "contrato — por exemplo, fiador junto com caução, ou fiador "
            "junto com seguro-fiança."
        ),
    },
    {
        "id": 3,
        "titulo": "Despesas extraordinárias de condomínio repassadas ao inquilino",
        "artigo": "Art. 22, X + Art. 25 + Art. 45",
        "descricao": (
            "Despesas extraordinárias de condomínio (obras estruturais, "
            "reformas, fachada, instalação de equipamentos de segurança "
            "ou lazer, fundo de reserva) são de responsabilidade do "
            "locador, não do locatário."
        ),
    },
    {
        "id": 4,
        "titulo": "Taxa de administração/intermediação cobrada do inquilino",
        "artigo": "Art. 22, VII",
        "descricao": (
            "As despesas de administração/intermediação da locação "
            "(comissão de imobiliária, taxa de agenciamento) são "
            "obrigação do locador, não podem ser repassadas ao locatário."
        ),
    },
    {
        "id": 5,
        "titulo": "Pintura nova obrigatória independente do estado do imóvel",
        "artigo": "Art. 23, III + Art. 45",
        "descricao": (
            "O locatário só é obrigado a devolver o imóvel pintado se essa "
            "necessidade estiver comprovada pelo estado real do imóvel — "
            "exigir pintura nova incondicionalmente ao final do contrato "
            "é cláusula abusiva."
        ),
    },
    {
        "id": 6,
        "titulo": "Reajuste com periodicidade menor que 12 meses",
        "artigo": "Regime de anualidade (Lei 9.069/95)",
        "descricao": (
            "O reajuste do valor do aluguel só pode ocorrer em intervalos "
            "mínimos de 12 (doze) meses."
        ),
    },
    {
        "id": 7,
        "titulo": "Cobrança antecipada de vários meses de aluguel (caução disfarçada)",
        "artigo": "Art. 38, §2º",
        "descricao": (
            "Exigir o pagamento antecipado de múltiplos meses de aluguel "
            "de uma vez funciona como uma caução disfarçada e está sujeito "
            "ao mesmo limite de 3 meses — independentemente do nome dado "
            "à cobrança (ex.: 'adiantamento de locativos')."
        ),
    },
]


def formatar_para_prompt() -> str:
    """Renderiza as 7 regras como texto numerado para o system prompt."""
    linhas = []
    for regra in REGRAS:
        linhas.append(
            f"{regra['id']}. {regra['titulo']} ({regra['artigo']})\n"
            f"   {regra['descricao']}"
        )
    return "\n".join(linhas)

# TrapDoor

Auditor de contrato de aluguel: cola o texto de um contrato de locação
residencial e recebe, por cláusula, quais das 7 regras da Lei do
Inquilinato (Lei 8.245/91) ele viola — e por quê.

Interface local em Streamlit, lógica em Python puro, uma única chamada
à API da Anthropic (saída forçada por schema, sem parse de markdown).

## As 7 regras

| # | Regra | Base legal |
|---|---|---|
| 1 | Caução em dinheiro acima de 3 meses de aluguel | Art. 38, §2º |
| 2 | Mais de uma garantia cumulada (fiador + caução + seguro-fiança) | Art. 37, parágrafo único |
| 3 | Despesas extraordinárias de condomínio repassadas ao inquilino | Art. 22, X + Art. 25 + Art. 45 |
| 4 | Taxa de administração/intermediação cobrada do inquilino | Art. 22, VII |
| 5 | Pintura nova obrigatória independente do estado do imóvel | Art. 23, III + Art. 45 |
| 6 | Reajuste com periodicidade menor que 12 meses | Regime de anualidade (Lei 9.069/95) |
| 7 | Cobrança antecipada de vários meses de aluguel (caução disfarçada) | Art. 38, §2º |

Fonte única das regras em `rules.py` — o mesmo texto alimenta o prompt
do modelo e o gabarito dos testes, para nunca divergirem. Uma cláusula
pode violar mais de uma regra ao mesmo tempo (`violacoes` é sempre uma
lista, nunca um campo único).

## Como rodar

```bash
python -m venv venv
venv\Scripts\activate        # Windows (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt

python -m streamlit run app.py
```

Copie `.env.example` para `.env` e preencha `ANTHROPIC_API_KEY` antes de rodar.

## Estrutura

```
app.py          # interface Streamlit
splitter.py     # split_clausulas(texto) -> list[str]
analyzer.py     # analisar(clausulas) -> list[dict], chamada à API
rules.py        # as 7 regras (dados) + formatação para o prompt
validar.py      # runner de teste: compara contra contratos/gabarito.json
contratos/      # contratos de teste sintéticos (sem dados reais) + gabarito
```

## Testes

`python validar.py` roda os 9 contratos de teste em `contratos/` contra
o gabarito esperado (`gabarito.json`) e retorna código de saída 0/1 —
inclui contratos limpos (checagem de falso positivo), contratos com
violação explícita e disfarçada, e um caso de regressão com duas
violações na mesma cláusula. Todos os documentos são sintéticos, com
nomes e números de documento fictícios.

## Licença

Ver [`LICENSE`](./LICENSE) — código proprietário, publicado para
avaliação de portfólio.

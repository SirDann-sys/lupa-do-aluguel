import pytest

from app.entrada.anonimizar import mascarar


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "inscrito no CPF sob nº 222.333.444-55, residente",
            "inscrito no CPF sob nº [CPF], residente",
        ),
        ("CPF 22233344455", "CPF [CPF]"),
        ("portador do RG nº 22.333.444-5, solteiro", "portador do RG nº [RG], solteiro"),
        ("RG 12345678X", "RG [RG]"),
        ("CNPJ 12.345.678/0001-90", "CNPJ [CNPJ]"),
        ("escreva para joao.silva+aluguel@exemplo.com.br", "escreva para [E-MAIL]"),
        ("telefone (62) 99966-9861", "telefone [TELEFONE]"),
        ("telefone +55 11 3456-7890", "telefone [TELEFONE]"),
        ("CEP 74000-120, Goiânia", "CEP [CEP], Goiânia"),
    ],
)
def test_mascara_dados_pessoais(texto: str, esperado: str) -> None:
    mascarado, total = mascarar(texto)
    assert mascarado == esperado
    assert total == 1


@pytest.mark.parametrize(
    "texto",
    [
        "O aluguel mensal é de R$ 2.000,00 (dois mil reais).",
        "Caução de R$ 15.000,00, equivalente a 5 (cinco) aluguéis.",
        "Prazo de 30 meses, com início em 01/10/2026 e término em 31/03/2029.",
        "CLÁUSULA 12 – nos termos do art. 22, VIII da Lei 8.245/91.",
        "Rua das Acácias, nº 350, apto 42, São Paulo/SP.",
        "Reajuste a cada 12 (doze) meses pelo IPCA.",
    ],
)
def test_nao_mexe_no_que_as_regras_precisam(texto: str) -> None:
    assert mascarar(texto) == (texto, 0)


def test_contrato_inteiro() -> None:
    from tests.conftest import CONTRATOS

    texto = (CONTRATOS / "03_abusivo_sutil.txt").read_text("utf-8")
    mascarado, total = mascarar(texto)
    assert total == 4  # 2 RGs e 2 CPFs na qualificação das partes
    assert "222.333.444-55" not in mascarado
    assert "R$ 8.400,00" in mascarado

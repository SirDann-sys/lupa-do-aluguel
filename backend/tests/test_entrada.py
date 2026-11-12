from io import BytesIO

import pytest
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.entrada.divisor import dividir
from app.entrada.pdf import extrair_texto
from app.erros import ArquivoInvalido, EntradaInvalida
from tests.conftest import CONTRATO_CURTO, CONTRATOS


def test_divide_por_clausula_e_descarta_preambulo() -> None:
    clausulas = dividir(CONTRATO_CURTO)
    assert len(clausulas) == 3
    assert clausulas[0].startswith("CLÁUSULA PRIMEIRA")
    assert all("CONTRATO DE LOCAÇÃO" not in c for c in clausulas)


def test_junta_quebras_de_linha_dentro_da_clausula() -> None:
    [clausula] = dividir("CLÁUSULA 1ª – DO ALUGUEL\nO aluguel mensal\né de R$ 1.000,00 por mês.")
    assert "\n" not in clausula
    assert "aluguel mensal é de" in clausula


def test_numeracao_sem_linhas_em_branco() -> None:
    texto = (CONTRATOS / "21_numerado_sem_paragrafos.txt").read_text("utf-8")
    clausulas = dividir(texto)
    assert len(clausulas) == 6
    assert clausulas[2].startswith("3. O aluguel será revisto")


def test_numero_no_meio_de_frase_nao_vira_marcador() -> None:
    texto = (
        "CLÁUSULA 1ª – DO REAJUSTE O aluguel será reajustado a cada\n"
        "12 meses pelo IPCA acumulado no período, conforme a lei."
    )
    assert len(dividir(texto)) == 1


def test_sem_marcadores_usa_paragrafos() -> None:
    texto = (
        "O aluguel mensal é de R$ 1.000,00 pago todo dia cinco.\n\n"
        "A garantia é um fiador com imóvel quitado na cidade."
    )
    assert len(dividir(texto)) == 2


def test_fragmentos_curtos_sao_ignorados() -> None:
    assert dividir("CLÁUSULA 1ª – FORO\nSalvador/BA.") == []


def test_texto_vazio() -> None:
    assert dividir("   \n\n  ") == []


def _pdf(paginas: list[str]) -> bytes:
    saida = BytesIO()
    tela = Canvas(saida, pagesize=A4)
    for texto in paginas:
        objeto = tela.beginText(40, 800)
        for linha in texto.splitlines():
            objeto.textLine(linha)
        tela.drawText(objeto)
        tela.showPage()
    tela.save()
    return saida.getvalue()


def test_extrai_texto_de_pdf() -> None:
    texto = extrair_texto(_pdf([CONTRATO_CURTO, CONTRATO_CURTO]), max_paginas=5)
    assert texto.count("CLÁUSULA SEGUNDA") == 2


def test_recusa_arquivo_que_nao_e_pdf() -> None:
    with pytest.raises(ArquivoInvalido):
        extrair_texto(b"PK\x03\x04 um zip qualquer", max_paginas=5)


def test_recusa_pdf_corrompido() -> None:
    with pytest.raises(ArquivoInvalido):
        extrair_texto(b"%PDF-1.7\nlixo sem estrutura", max_paginas=5)


def test_recusa_pdf_com_paginas_demais() -> None:
    with pytest.raises(EntradaInvalida, match="3 páginas"):
        extrair_texto(_pdf([CONTRATO_CURTO] * 3), max_paginas=2)


def test_recusa_pdf_sem_texto() -> None:
    with pytest.raises(EntradaInvalida, match="digitalizado"):
        extrair_texto(_pdf([""]), max_paginas=5)


def test_recusa_pdf_com_senha() -> None:
    escritor = PdfWriter(clone_from=BytesIO(_pdf([CONTRATO_CURTO])))
    escritor.encrypt("segredo")
    saida = BytesIO()
    escritor.write(saida)
    with pytest.raises(ArquivoInvalido, match="senha"):
        extrair_texto(saida.getvalue(), max_paginas=5)

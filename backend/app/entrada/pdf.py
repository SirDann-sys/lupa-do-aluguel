"""Extração de texto de PDF.

Só PDFs com texto selecionável: um contrato escaneado (imagem) não tem texto
para extrair, e o usuário recebe uma mensagem clara em vez de um relatório
vazio que pareceria "nenhuma cláusula abusiva".
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.erros import ArquivoInvalido, EntradaInvalida

ASSINATURA_PDF = b"%PDF-"
MINIMO_CARACTERES = 200


def extrair_texto(conteudo: bytes, max_paginas: int) -> str:
    if not conteudo.startswith(ASSINATURA_PDF):
        raise ArquivoInvalido("O arquivo enviado não é um PDF.")

    try:
        leitor = PdfReader(BytesIO(conteudo))
        if leitor.is_encrypted:
            raise ArquivoInvalido("O PDF está protegido por senha.")
        paginas = leitor.pages
        if len(paginas) > max_paginas:
            raise EntradaInvalida(f"O PDF tem {len(paginas)} páginas; o limite é {max_paginas}.")
        texto = "\n\n".join((p.extract_text() or "").strip() for p in paginas)
    except PdfReadError as erro:
        raise ArquivoInvalido("Não foi possível ler o PDF.") from erro

    if len(texto.strip()) < MINIMO_CARACTERES:
        raise EntradaInvalida(
            "O PDF não tem texto selecionável (parece digitalizado como imagem). "
            "Copie o texto do contrato e cole na caixa de texto."
        )
    return texto

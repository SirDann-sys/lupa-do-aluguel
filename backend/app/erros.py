"""Erros da aplicação. Cada um vira uma resposta HTTP com código estável."""


class ErroLupa(Exception):
    status = 500
    codigo = "erro_interno"

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalida(ErroLupa):
    status = 422
    codigo = "entrada_invalida"


class ArquivoInvalido(ErroLupa):
    status = 415
    codigo = "arquivo_invalido"


class LimiteExcedido(ErroLupa):
    status = 429
    codigo = "limite_excedido"

    def __init__(self, mensagem: str, tentar_em_segundos: int) -> None:
        super().__init__(mensagem)
        self.tentar_em_segundos = tentar_em_segundos


class ProvedoresIndisponiveis(ErroLupa):
    status = 503
    codigo = "provedores_indisponiveis"

"""Modelos do domínio.

`FatosClausula` é o contrato entre a extração (LLM ou heurística) e as regras:
a extração só descreve *o que a cláusula diz*; quem decide se isso é ilegal
são as funções de `regras.py`. Nenhum campo aqui carrega juízo jurídico.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TipoGarantia(StrEnum):
    """Modalidades de garantia do art. 37 da Lei 8.245/91."""

    CAUCAO = "caucao"
    FIADOR = "fiador"
    SEGURO_FIANCA = "seguro_fianca"
    CESSAO_QUOTAS = "cessao_quotas"


class Campo(StrEnum):
    """Campos de `FatosClausula` que precisam de evidência literal."""

    GARANTIAS = "garantias"
    CAUCAO = "caucao"
    ALUGUEL_MENSAL = "aluguel_mensal"
    ALUGUEL_ANTECIPADO = "aluguel_antecipado"
    REAJUSTE = "reajuste"
    DESPESAS_EXTRAORDINARIAS = "despesas_extraordinarias"
    TAXA_IMOBILIARIA = "taxa_imobiliaria"
    PINTURA_INCONDICIONAL = "pintura_incondicional"


class Evidencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campo: Campo
    trecho: str = Field(description="Trecho copiado literalmente da cláusula.")


class FatosClausula(BaseModel):
    """O que uma cláusula estabelece, sem avaliação jurídica."""

    model_config = ConfigDict(extra="forbid")

    indice: int = Field(ge=1, description="Número da cláusula na lista enviada.")
    garantias: list[TipoGarantia] = Field(
        default_factory=list,
        description="Garantias exigidas do locatário NESTA cláusula.",
    )
    caucao_meses: float | None = Field(None, ge=0, description="Caução em meses de aluguel.")
    caucao_valor: float | None = Field(None, ge=0, description="Caução em reais.")
    aluguel_mensal: float | None = Field(None, ge=0, description="Valor do aluguel mensal.")
    aluguel_antecipado_meses: float | None = Field(
        None, ge=0, description="Meses de aluguel cobrados antecipadamente."
    )
    aluguel_antecipado_valor: float | None = Field(
        None, ge=0, description="Valor em reais cobrado como aluguel antecipado."
    )
    reajuste_periodicidade_meses: int | None = Field(
        None, ge=0, description="Intervalo entre reajustes do aluguel, em meses."
    )
    inquilino_paga_despesas_extraordinarias: bool = False
    inquilino_paga_taxa_imobiliaria: bool = False
    pintura_obrigatoria_incondicional: bool = False
    evidencias: list[Evidencia] = Field(default_factory=list)


class RespostaExtracao(BaseModel):
    """Formato exigido do LLM: um item por cláusula enviada."""

    model_config = ConfigDict(extra="forbid")

    clausulas: list[FatosClausula]


class Achado(BaseModel):
    """Uma violação de regra, apontando as cláusulas e os trechos que a provam."""

    regra: int
    titulo: str
    artigo: str
    explicacao: str
    orientacao: str
    clausulas: list[int]
    trechos: list[str]


class ClausulaRelatorio(BaseModel):
    indice: int
    texto: str
    regras: list[int]


class Relatorio(BaseModel):
    clausulas: list[ClausulaRelatorio]
    achados: list[Achado]
    provedor: str
    modelo: str
    fatos_descartados: int = Field(
        description="Fatos ignorados porque a evidência não foi encontrada no texto."
    )
    dados_mascarados: int = Field(
        0, description="CPF, RG, CNPJ, e-mail, telefone e CEP trocados por marcadores antes da IA."
    )
    em_cache: bool = False
    aviso: str

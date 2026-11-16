"""Formatos de entrada e de saída da API, usados na validação e na documentação (/docs)."""

from datetime import date, datetime

from pydantic import BaseModel, Field


# Livros ---------------------------------------------------------------------------------------

class AutorDaFicha(BaseModel):
    id: int
    nome: str
    nacionalidade: str


class CategoriaDaFicha(BaseModel):
    id: int
    nome: str


class OutroLivroDoAutor(BaseModel):
    id: int
    titulo: str
    ano_publicacao: int


class Circulacao(BaseModel):
    total_emprestimos: int
    ultimo_emprestimo: datetime | None


class FichaDoLivro(BaseModel):
    """Dados de catálogo do livro: é o que vai para o cache."""

    id: int
    titulo: str
    isbn: str
    editora: str
    ano_publicacao: int
    paginas: int
    sinopse: str
    total_exemplares: int
    autor: AutorDaFicha
    categoria: CategoriaDaFicha
    outros_livros_do_autor: list[OutroLivroDoAutor]
    circulacao: Circulacao
    atualizado_em: datetime = Field(description="Última alteração do livro no banco.")
    gerada_em: datetime = Field(
        description="Momento em que a ficha foi montada a partir do banco. Se a resposta veio "
        "do cache, é o momento em que ela foi guardada."
    )


class Disponibilidade(BaseModel):
    """Dado volátil (muda a cada empréstimo): sempre lido do banco, nunca do cache."""

    livro_id: int
    total_exemplares: int
    exemplares_disponiveis: int
    disponivel: bool


class AtualizacaoDoLivro(BaseModel):
    """Campos de catálogo que podem ser alterados. Os ausentes ficam como estão."""

    titulo: str | None = Field(None, min_length=1, max_length=200)
    editora: str | None = Field(None, min_length=1, max_length=80)
    sinopse: str | None = Field(None, min_length=1)
    paginas: int | None = Field(None, gt=0, le=32767)
    ano_publicacao: int | None = Field(None, ge=1000, le=2100)


# Empréstimos ----------------------------------------------------------------------------------

class LivroDoEmprestimo(BaseModel):
    id: int
    titulo: str


class LeitorDoEmprestimo(BaseModel):
    id: int
    nome: str


class EmprestimoDetalhado(BaseModel):
    id: int
    data_emprestimo: datetime
    data_prevista: date
    data_devolucao: datetime | None
    livro: LivroDoEmprestimo
    leitor: LeitorDoEmprestimo


class EmprestimoResumido(BaseModel):
    id: int
    livro_id: int
    leitor_id: int
    data_emprestimo: datetime
    data_prevista: date
    data_devolucao: datetime | None


class NovoEmprestimo(BaseModel):
    livro_id: int = Field(gt=0)
    leitor_id: int = Field(gt=0)


class EmprestimoRegistrado(EmprestimoResumido):
    exemplares_disponiveis: int


class EmprestimoAtrasado(BaseModel):
    id: int
    data_emprestimo: datetime
    data_prevista: date
    dias_de_atraso: int
    livro: LivroDoEmprestimo
    leitor: LeitorDoEmprestimo


# Leitores -------------------------------------------------------------------------------------

class ItemDoHistorico(BaseModel):
    id: int
    data_emprestimo: datetime
    data_prevista: date
    data_devolucao: datetime | None
    livro: LivroDoEmprestimo


class HistoricoDoLeitor(BaseModel):
    leitor_id: int
    quantidade: int
    emprestimos: list[ItemDoHistorico]

"""Mapeamento objeto-relacional (SQLAlchemy) das tabelas da biblioteca.

O relacionamento comparado no item 2 do trabalho é Empréstimo -> Livro e Empréstimo -> Leitor.
A estratégia de carregamento fica declarada no mapeamento, como o FetchType do JPA:

    lazy="select"  ->  LAZY: o livro só é buscado quando o código acessa emprestimo.livro
    lazy="joined"  ->  EAGER: o livro vem junto, com JOIN, na mesma consulta do empréstimo

Por isso a tabela emprestimo é mapeada duas vezes: Emprestimo (LAZY, usado em toda a API) e
EmprestimoEager (EAGER, só leitura, usado na comparação).
"""

from datetime import date, datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]


class Autor(Base):
    __tablename__ = "autor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    nacionalidade: Mapped[str]


class Livro(Base):
    __tablename__ = "livro"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str]
    isbn: Mapped[str]
    editora: Mapped[str]
    ano_publicacao: Mapped[int]
    paginas: Mapped[int]
    sinopse: Mapped[str]
    autor_id: Mapped[int] = mapped_column(ForeignKey("autor.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    total_exemplares: Mapped[int]
    exemplares_disponiveis: Mapped[int]
    atualizado_em: Mapped[datetime]

    autor: Mapped[Autor] = relationship(lazy="select")
    categoria: Mapped[Categoria] = relationship(lazy="select")


class Leitor(Base):
    __tablename__ = "leitor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    email: Mapped[str]
    cadastrado_em: Mapped[date]


class Emprestimo(Base):
    """Empréstimo com carregamento LAZY (sob demanda) do livro e do leitor."""

    __tablename__ = "emprestimo"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livro.id"))
    leitor_id: Mapped[int] = mapped_column(ForeignKey("leitor.id"))
    data_emprestimo: Mapped[datetime]
    data_prevista: Mapped[date]
    data_devolucao: Mapped[datetime | None]

    livro: Mapped[Livro] = relationship(lazy="select")
    leitor: Mapped[Leitor] = relationship(lazy="select")


class EmprestimoEager(Base):
    """A mesma tabela emprestimo, com carregamento EAGER (antecipado) do livro e do leitor."""

    __table__ = Emprestimo.__table__

    livro: Mapped[Livro] = relationship(lazy="joined", viewonly=True)
    leitor: Mapped[Leitor] = relationship(lazy="joined", viewonly=True)

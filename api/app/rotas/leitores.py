"""Seção 5 do trabalho (índices): histórico de empréstimos de um leitor.

    SELECT ... FROM emprestimo JOIN livro ON livro.id = emprestimo.livro_id
    WHERE emprestimo.leitor_id = ?
    ORDER BY emprestimo.data_emprestimo DESC

No estado inicial do banco não há índice em emprestimo(leitor_id): o PostgreSQL lê a tabela
inteira (300 mil linhas) para achar os empréstimos de um leitor e depois os ordena. O índice
(leitor_id, data_emprestimo DESC) entrega as linhas do leitor já na ordem pedida.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select

from ..banco import Sessao
from ..esquemas import HistoricoDoLeitor
from ..modelos import Emprestimo, Leitor, Livro
from ..respostas import RespostaJSON

rotas = APIRouter(prefix="/api/leitores", tags=["Leitores (item 2: índices)"])


def consulta_historico(leitor_id: int, limite: int | None = None):
    consulta = (
        select(
            Emprestimo.id,
            Emprestimo.data_emprestimo,
            Emprestimo.data_prevista,
            Emprestimo.data_devolucao,
            Livro.id.label("livro_id"),
            Livro.titulo,
        )
        .join(Livro, Livro.id == Emprestimo.livro_id)
        .where(Emprestimo.leitor_id == leitor_id)
        .order_by(Emprestimo.data_emprestimo.desc())
    )
    return consulta if limite is None else consulta.limit(limite)


def montar_historico(sessao, leitor_id: int, limite: int | None = None) -> dict | None:
    linhas = sessao.execute(consulta_historico(leitor_id, limite)).all()
    if not linhas and sessao.get(Leitor, leitor_id) is None:
        return None
    return {
        "leitor_id": leitor_id,
        "quantidade": len(linhas),
        "emprestimos": [
            {
                "id": l.id,
                "data_emprestimo": l.data_emprestimo,
                "data_prevista": l.data_prevista,
                "data_devolucao": l.data_devolucao,
                "livro": {"id": l.livro_id, "titulo": l.titulo},
            }
            for l in linhas
        ],
    }


@rotas.get(
    "/{leitor_id}/emprestimos",
    response_model=HistoricoDoLeitor,
    summary="Histórico de empréstimos do leitor",
)
def historico(
    leitor_id: Annotated[int, Path(gt=0, description="Id do leitor (1 a 10.000).")],
    limite: Annotated[int | None, Query(ge=1, le=1000, description="Só os N mais recentes.")] = None,
):
    """Empréstimos do leitor, do mais recente ao mais antigo, com o título do livro. Sem
    `limite`, devolve todos (é a consulta usada no experimento de índices)."""
    with Sessao() as sessao:
        resultado = montar_historico(sessao, leitor_id, limite)
    if resultado is None:
        raise HTTPException(404, "Leitor não encontrado.")
    return RespostaJSON(resultado)

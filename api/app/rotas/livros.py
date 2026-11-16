"""Item 1 do trabalho: ficha do livro sem cache e com cache, alteração e invalidação.

A ficha reúne os dados de catálogo do livro (título, autor, categoria, sinopse...), o total de
empréstimos e outros livros do mesmo autor. Montá-la custa três consultas ao banco. Ela é muito
lida e quase não muda, por isso vai para o cache.

A disponibilidade (exemplares disponíveis) muda a cada empréstimo e um valor velho engana o
leitor, então fica numa rota à parte e é sempre lida do banco.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .. import cache
from ..banco import Sessao
from ..esquemas import AtualizacaoDoLivro, Disponibilidade, FichaDoLivro
from ..modelos import Emprestimo, Livro
from ..respostas import RespostaJSON, para_json

rotas = APIRouter(prefix="/api/livros", tags=["Livros (item 1: cache)"])

IdDoLivro = Annotated[int, Path(gt=0, description="Id do livro (de 1 a 20.000 nos dados gerados).")]


def montar_ficha(sessao, livro_id: int) -> dict | None:
    """Monta a ficha a partir do banco, com três consultas."""
    # 1. o livro com o autor e a categoria, numa consulta com JOIN
    livro = sessao.scalars(
        select(Livro)
        .options(joinedload(Livro.autor), joinedload(Livro.categoria))
        .where(Livro.id == livro_id)
    ).one_or_none()
    if livro is None:
        return None

    # 2. quantas vezes o livro já foi emprestado e quando foi a última vez
    total_emprestimos, ultimo_emprestimo = sessao.execute(
        select(func.count(), func.max(Emprestimo.data_emprestimo))
        .where(Emprestimo.livro_id == livro_id)
    ).one()

    # 3. até cinco outros livros do mesmo autor, dos mais recentes aos mais antigos
    outros = sessao.execute(
        select(Livro.id, Livro.titulo, Livro.ano_publicacao)
        .where(Livro.autor_id == livro.autor_id, Livro.id != livro_id)
        .order_by(Livro.ano_publicacao.desc(), Livro.id)
        .limit(5)
    ).all()

    return {
        "id": livro.id,
        "titulo": livro.titulo,
        "isbn": livro.isbn,
        "editora": livro.editora,
        "ano_publicacao": livro.ano_publicacao,
        "paginas": livro.paginas,
        "sinopse": livro.sinopse,
        "total_exemplares": livro.total_exemplares,
        "autor": {
            "id": livro.autor.id,
            "nome": livro.autor.nome,
            "nacionalidade": livro.autor.nacionalidade,
        },
        "categoria": {"id": livro.categoria.id, "nome": livro.categoria.nome},
        "outros_livros_do_autor": [
            {"id": o.id, "titulo": o.titulo, "ano_publicacao": o.ano_publicacao} for o in outros
        ],
        "circulacao": {
            "total_emprestimos": total_emprestimos,
            "ultimo_emprestimo": ultimo_emprestimo,
        },
        "atualizado_em": livro.atualizado_em,
        "gerada_em": datetime.now(),
    }


def _ficha_do_banco(livro_id: int) -> dict:
    with Sessao() as sessao:
        ficha = montar_ficha(sessao, livro_id)
    if ficha is None:
        raise HTTPException(404, "Livro não encontrado.")
    return ficha


@rotas.get("/{livro_id}/sem-cache", response_model=FichaDoLivro, summary="Ficha do livro, sem cache")
def ficha_sem_cache(livro_id: IdDoLivro):
    """Cenário A: toda requisição consulta o banco (três consultas)."""
    return RespostaJSON(_ficha_do_banco(livro_id))


@rotas.get(
    "/{livro_id}/com-cache",
    response_model=FichaDoLivro,
    summary="Ficha do livro, com cache",
    responses={200: {"headers": {"X-Cache": {"description": "HIT (veio do cache) ou MISS (veio do banco)"}}}},
)
def ficha_com_cache(livro_id: IdDoLivro):
    """Cenário B: procura a ficha no Redis; se não está lá, monta a partir do banco e guarda
    com o TTL configurado. O cabeçalho `X-Cache` diz de onde veio a resposta."""
    chave = cache.chave_do_livro(livro_id)
    guardada = cache.ler(chave)
    if guardada is not None:
        return RespostaJSON(guardada, headers={"X-Cache": "HIT"})

    corpo = para_json(_ficha_do_banco(livro_id))
    cache.gravar(chave, corpo)
    return RespostaJSON(corpo, headers={"X-Cache": "MISS"})


@rotas.put("/{livro_id}", response_model=FichaDoLivro, summary="Altera o livro e invalida o cache")
def atualizar_livro(livro_id: IdDoLivro, dados: AtualizacaoDoLivro):
    """Altera dados de catálogo e, depois do commit, apaga a ficha do cache: a próxima leitura
    com cache já busca a versão nova. Devolve a ficha atualizada, lida do banco.

    A remoção acontece só depois do commit; antes dele, uma leitura simultânea poderia
    guardar de novo no cache o valor antigo."""
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(422, "Informe ao menos um campo para alterar.")

    with Sessao.begin() as sessao:
        livro = sessao.get(Livro, livro_id)
        if livro is None:
            raise HTTPException(404, "Livro não encontrado.")
        for nome, valor in campos.items():
            setattr(livro, nome, valor)
        livro.atualizado_em = datetime.now()

    # X-Cache-Invalidado: "sim" se a ficha estava no cache e foi apagada
    invalidou = cache.invalidar(cache.chave_do_livro(livro_id))
    return RespostaJSON(
        _ficha_do_banco(livro_id), headers={"X-Cache-Invalidado": "sim" if invalidou else "nao"}
    )


@rotas.get(
    "/{livro_id}/disponibilidade",
    response_model=Disponibilidade,
    summary="Exemplares disponíveis (sempre do banco)",
)
def disponibilidade(livro_id: IdDoLivro):
    """Dado volátil, alterado a cada empréstimo e devolução: não passa pelo cache."""
    with Sessao() as sessao:
        linha = sessao.execute(
            select(Livro.total_exemplares, Livro.exemplares_disponiveis).where(Livro.id == livro_id)
        ).one_or_none()
    if linha is None:
        raise HTTPException(404, "Livro não encontrado.")
    return RespostaJSON({
        "livro_id": livro_id,
        "total_exemplares": linha.total_exemplares,
        "exemplares_disponiveis": linha.exemplares_disponiveis,
        "disponivel": linha.exemplares_disponiveis > 0,
    })

"""Item 1 do trabalho: ficha do livro sem cache e com cache, alteração e invalidação.

A ficha reúne os dados de catálogo do livro (título, autor, categoria, sinopse...), o total de
empréstimos e outros livros do mesmo autor. Montá-la custa três consultas ao banco. Ela é muito
lida e quase não muda, por isso vai para o cache.

A disponibilidade (exemplares disponíveis) muda a cada empréstimo e um valor velho engana o
leitor, então fica numa rota à parte e é sempre lida do banco.
"""

from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from .. import cache
from ..banco import Sessao, SessaoLeitura
from ..esquemas import AtualizacaoDoLivro, Disponibilidade, FichaDoLivro
from ..modelos import Emprestimo, Livro
from ..respostas import RespostaJSON, para_json

rotas = APIRouter(prefix="/api/livros", tags=["Livros (item 1: cache)"])

IdDoLivro = Annotated[int, Path(gt=0, description="Id do livro (de 1 a 20.000 nos dados gerados).")]


def _compor_ficha(livro, total_emprestimos, ultimo_emprestimo, outros) -> dict:
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

    return _compor_ficha(livro, total_emprestimos, ultimo_emprestimo, outros)


def montar_fichas(sessao) -> list[dict]:
    """As fichas de todos os livros de uma vez, com duas consultas no total. Serve para encher o
    cache antes dos testes de carga (rota de laboratório): ficha por ficha, o conteúdo é o mesmo
    de montar_ficha, que faria 60.000 consultas para os 20.000 livros."""
    livros = sessao.scalars(
        select(Livro).options(joinedload(Livro.autor), joinedload(Livro.categoria)).order_by(Livro.id)
    ).all()
    circulacao = {
        livro_id: (total, ultimo)
        for livro_id, total, ultimo in sessao.execute(
            select(Emprestimo.livro_id, func.count(), func.max(Emprestimo.data_emprestimo))
            .group_by(Emprestimo.livro_id)
        )
    }
    # outros livros do autor na mesma ordem da consulta 3 de montar_ficha
    por_autor = defaultdict(list)
    for livro in livros:
        por_autor[livro.autor_id].append(livro)
    for obras in por_autor.values():
        obras.sort(key=lambda obra: (-obra.ano_publicacao, obra.id))

    fichas = []
    for livro in livros:
        outros = [obra for obra in por_autor[livro.autor_id] if obra.id != livro.id][:5]
        total, ultimo = circulacao.get(livro.id, (0, None))
        fichas.append(_compor_ficha(livro, total, ultimo, outros))
    return fichas


def _ficha_do_banco(livro_id: int) -> dict:
    with SessaoLeitura() as sessao:
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
    responses={200: {"headers": {"X-Cache": {
        "description": "HIT (veio do cache), MISS (veio do banco e foi guardada) ou INDISPONIVEL "
                       "(o Redis não respondeu: veio do banco, como na versão sem cache)",
    }}}},
)
def ficha_com_cache(livro_id: IdDoLivro):
    """Cenário B: procura a ficha no Redis; se não está lá, monta a partir do banco e guarda
    com o TTL configurado. O cabeçalho `X-Cache` diz de onde veio a resposta.

    O cache é só um atalho: se o Redis não responder, a ficha vem do banco (`X-Cache:
    INDISPONIVEL`) em vez de a requisição falhar."""
    chave = cache.chave_do_livro(livro_id)
    try:
        guardada = cache.ler(chave)
    except cache.CacheIndisponivel:
        return RespostaJSON(_ficha_do_banco(livro_id), headers={"X-Cache": "INDISPONIVEL"})
    if guardada is not None:
        return RespostaJSON(guardada, headers={"X-Cache": "HIT"})

    corpo = para_json(_ficha_do_banco(livro_id))
    try:
        cache.gravar(chave, corpo)
    except cache.CacheIndisponivel:
        return RespostaJSON(corpo, headers={"X-Cache": "INDISPONIVEL"})
    return RespostaJSON(corpo, headers={"X-Cache": "MISS"})


@rotas.put(
    "/{livro_id}",
    response_model=FichaDoLivro,
    summary="Altera o livro e invalida o cache",
    responses={200: {"headers": {"X-Cache-Invalidado": {
        "description": "sim (a ficha estava no cache e foi apagada), nao (não estava) ou pendente "
                       "(o Redis não respondeu: a ficha será apagada assim que ele voltar)",
    }}}},
)
def atualizar_livro(livro_id: IdDoLivro, dados: AtualizacaoDoLivro):
    """Altera dados de catálogo e, depois do commit, apaga a ficha do cache: a próxima leitura
    com cache já busca a versão nova. Devolve a ficha atualizada, lida do banco.

    A remoção acontece só depois do commit; antes dele, uma leitura simultânea poderia
    guardar de novo no cache o valor antigo. Se o Redis não responder, a alteração continua
    valendo (ela já está no banco) e a remoção fica pendente até ele voltar."""
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
    try:
        invalidado = "sim" if cache.invalidar(cache.chave_do_livro(livro_id)) else "nao"
    except cache.CacheIndisponivel:
        invalidado = "pendente"
    return RespostaJSON(_ficha_do_banco(livro_id), headers={"X-Cache-Invalidado": invalidado})


@rotas.get(
    "/{livro_id}/disponibilidade",
    response_model=Disponibilidade,
    summary="Exemplares disponíveis (sempre do banco)",
)
def disponibilidade(livro_id: IdDoLivro):
    """Dado volátil, alterado a cada empréstimo e devolução: não passa pelo cache."""
    with SessaoLeitura() as sessao:
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

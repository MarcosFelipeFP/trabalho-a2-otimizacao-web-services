"""Item 2 do trabalho: a mesma listagem de empréstimos com estratégias de carregamento diferentes.

Todas as versões devolvem exatamente o mesmo JSON: uma página de empréstimos, cada um com o
título do livro e o nome do leitor. Muda só a forma de buscar os dados:

    lazy             mapeamento LAZY; livro e leitor buscados ao serem acessados (N+1)
    eager            mapeamento EAGER (lazy="joined"); tudo numa consulta com JOIN
    eager-selectin   EAGER com outra forma de busca: 1 consulta + 1 por relacionamento (IN)
    eager-immediate  EAGER que busca cada livro e cada leitor logo após carregar a página (N+1)
    join-fetch       consulta LAZY com joinedload, o equivalente ao JOIN FETCH do JPQL
    otimizada        projeção: uma consulta com JOIN que traz só as colunas usadas na resposta
    nativa           a mesma consulta da otimizada, escrita à mão em SQL

Também aqui ficam o registro de empréstimo e de devolução e a lista de empréstimos atrasados.
"""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select, text
from sqlalchemy.orm import immediateload, joinedload, selectinload

from ..banco import Sessao
from ..esquemas import (
    EmprestimoAtrasado,
    EmprestimoDetalhado,
    EmprestimoRegistrado,
    EmprestimoResumido,
    NovoEmprestimo,
)
from ..modelos import Emprestimo, EmprestimoEager, Leitor, Livro
from ..respostas import RespostaJSON

rotas = APIRouter(prefix="/api/emprestimos", tags=["Empréstimos (item 2: EAGER x LAZY)"])

DesdeId = Annotated[int, Query(ge=1, description="Id do primeiro empréstimo da página.")]
Quantidade = Annotated[int, Query(ge=1, le=1000, description="Quantos empréstimos listar.")]


# Conversão para o formato da resposta -----------------------------------------------------------

def _detalhado(e) -> dict:
    """Converte a entidade. No LAZY, é aqui que saem as consultas extras: ler e.livro e
    e.leitor pela primeira vez faz o SQLAlchemy buscar o livro e o leitor no banco."""
    return {
        "id": e.id,
        "data_emprestimo": e.data_emprestimo,
        "data_prevista": e.data_prevista,
        "data_devolucao": e.data_devolucao,
        "livro": {"id": e.livro.id, "titulo": e.livro.titulo},
        "leitor": {"id": e.leitor.id, "nome": e.leitor.nome},
    }


def _detalhado_da_linha(linha) -> dict:
    """Converte uma linha de projeção (sem entidades)."""
    return {
        "id": linha.id,
        "data_emprestimo": linha.data_emprestimo,
        "data_prevista": linha.data_prevista,
        "data_devolucao": linha.data_devolucao,
        "livro": {"id": linha.livro_id, "titulo": linha.titulo},
        "leitor": {"id": linha.leitor_id, "nome": linha.nome},
    }


def _resumido(e) -> dict:
    return {
        "id": e.id,
        "livro_id": e.livro_id,
        "leitor_id": e.leitor_id,
        "data_emprestimo": e.data_emprestimo,
        "data_prevista": e.data_prevista,
        "data_devolucao": e.data_devolucao,
    }


def _pagina(entidade, desde_id: int, quantidade: int):
    return (
        select(entidade)
        .where(entidade.id >= desde_id)
        .order_by(entidade.id)
        .limit(quantidade)
    )


# As estratégias -------------------------------------------------------------------------------

def listar_lazy(sessao, desde_id, quantidade):
    emprestimos = sessao.scalars(_pagina(Emprestimo, desde_id, quantidade)).all()
    return [_detalhado(e) for e in emprestimos]


def listar_eager(sessao, desde_id, quantidade):
    emprestimos = sessao.scalars(_pagina(EmprestimoEager, desde_id, quantidade)).all()
    return [_detalhado(e) for e in emprestimos]


def listar_eager_selectin(sessao, desde_id, quantidade):
    consulta = _pagina(Emprestimo, desde_id, quantidade).options(
        selectinload(Emprestimo.livro), selectinload(Emprestimo.leitor)
    )
    return [_detalhado(e) for e in sessao.scalars(consulta).all()]


def listar_eager_immediate(sessao, desde_id, quantidade):
    consulta = _pagina(Emprestimo, desde_id, quantidade).options(
        immediateload(Emprestimo.livro), immediateload(Emprestimo.leitor)
    )
    return [_detalhado(e) for e in sessao.scalars(consulta).all()]


def listar_join_fetch(sessao, desde_id, quantidade):
    consulta = _pagina(Emprestimo, desde_id, quantidade).options(
        joinedload(Emprestimo.livro), joinedload(Emprestimo.leitor)
    )
    return [_detalhado(e) for e in sessao.scalars(consulta).all()]


def listar_otimizada(sessao, desde_id, quantidade):
    consulta = (
        select(
            Emprestimo.id,
            Emprestimo.data_emprestimo,
            Emprestimo.data_prevista,
            Emprestimo.data_devolucao,
            Livro.id.label("livro_id"),
            Livro.titulo,
            Leitor.id.label("leitor_id"),
            Leitor.nome,
        )
        .join(Livro, Livro.id == Emprestimo.livro_id)
        .join(Leitor, Leitor.id == Emprestimo.leitor_id)
        .where(Emprestimo.id >= desde_id)
        .order_by(Emprestimo.id)
        .limit(quantidade)
    )
    return [_detalhado_da_linha(linha) for linha in sessao.execute(consulta)]


SQL_NATIVO = text("""
    SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao,
           l.id AS livro_id, l.titulo, r.id AS leitor_id, r.nome
    FROM emprestimo e
    JOIN livro l ON l.id = e.livro_id
    JOIN leitor r ON r.id = e.leitor_id
    WHERE e.id >= :desde_id
    ORDER BY e.id
    LIMIT :quantidade
""")


def listar_nativa(sessao, desde_id, quantidade):
    linhas = sessao.execute(SQL_NATIVO, {"desde_id": desde_id, "quantidade": quantidade})
    return [_detalhado_da_linha(linha) for linha in linhas]


ESTRATEGIAS = {
    "lazy": listar_lazy,
    "eager": listar_eager,
    "eager-selectin": listar_eager_selectin,
    "eager-immediate": listar_eager_immediate,
    "join-fetch": listar_join_fetch,
    "otimizada": listar_otimizada,
    "nativa": listar_nativa,
}


# Versões "resumo": a resposta não usa o livro nem o leitor ------------------------------------

def resumir_lazy(sessao, desde_id, quantidade):
    return [_resumido(e) for e in sessao.scalars(_pagina(Emprestimo, desde_id, quantidade))]


def resumir_eager(sessao, desde_id, quantidade):
    return [_resumido(e) for e in sessao.scalars(_pagina(EmprestimoEager, desde_id, quantidade))]


ESTRATEGIAS_RESUMO = {"lazy": resumir_lazy, "eager": resumir_eager}


def _listar(funcao, desde_id, quantidade):
    with Sessao() as sessao:
        return RespostaJSON(funcao(sessao, desde_id, quantidade))


# Rotas da comparação --------------------------------------------------------------------------

@rotas.get("/lazy", response_model=list[EmprestimoDetalhado], summary="LAZY (problema N+1)")
def emprestimos_lazy(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """1 consulta para a página e, ao montar a resposta, 1 para cada livro e 1 para cada
    leitor ainda não carregados: até 1 + 2N consultas."""
    return _listar(listar_lazy, desde_id, quantidade)


@rotas.get("/eager", response_model=list[EmprestimoDetalhado], summary="EAGER (lazy=\"joined\")")
def emprestimos_eager(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """O mapeamento EAGER faz o SQLAlchemy acrescentar LEFT OUTER JOIN com livro e leitor a
    toda consulta de empréstimos, com todas as colunas das duas tabelas."""
    return _listar(listar_eager, desde_id, quantidade)


@rotas.get("/eager-selectin", response_model=list[EmprestimoDetalhado], summary="EAGER com SELECT ... IN")
def emprestimos_eager_selectin(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """Carregamento antecipado em consultas separadas: 1 para a página, 1 para todos os livros
    (WHERE id IN ...) e 1 para todos os leitores. EAGER não significa uma consulta só."""
    return _listar(listar_eager_selectin, desde_id, quantidade)


@rotas.get("/eager-immediate", response_model=list[EmprestimoDetalhado], summary="EAGER com N+1")
def emprestimos_eager_immediate(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """Carregamento antecipado que busca cada livro e cada leitor logo depois da página, um por
    vez: o mesmo N+1 do LAZY, só que antes de a resposta ser montada."""
    return _listar(listar_eager_immediate, desde_id, quantidade)


@rotas.get("/join-fetch", response_model=list[EmprestimoDetalhado], summary="JOIN FETCH (joinedload)")
def emprestimos_join_fetch(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """Mapeamento LAZY, mas esta consulta pede o livro e o leitor com JOIN (joinedload), como
    o JOIN FETCH do JPQL. Gera o mesmo SQL do EAGER, sem impor o JOIN às outras consultas."""
    return _listar(listar_join_fetch, desde_id, quantidade)


@rotas.get("/otimizada", response_model=list[EmprestimoDetalhado], summary="Otimizada (projeção)")
def emprestimos_otimizada(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """Uma consulta com JOIN que traz só as oito colunas usadas na resposta (projeção/DTO), sem
    criar entidades."""
    return _listar(listar_otimizada, desde_id, quantidade)


@rotas.get("/nativa", response_model=list[EmprestimoDetalhado], summary="SQL nativo")
def emprestimos_nativa(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """A mesma consulta da versão otimizada, escrita à mão em SQL (text())."""
    return _listar(listar_nativa, desde_id, quantidade)


@rotas.get("/lazy/resumo", response_model=list[EmprestimoResumido], summary="Só os empréstimos, LAZY")
def resumo_lazy(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """A resposta não usa livro nem leitor: com LAZY, uma consulta só na tabela emprestimo."""
    return _listar(resumir_lazy, desde_id, quantidade)


@rotas.get("/eager/resumo", response_model=list[EmprestimoResumido], summary="Só os empréstimos, EAGER")
def resumo_eager(desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    """A mesma resposta com o mapeamento EAGER: o JOIN com livro e leitor acontece mesmo assim,
    e todas as colunas das duas tabelas vêm do banco sem serem usadas."""
    return _listar(resumir_eager, desde_id, quantidade)


# Busca por intervalo (seção 5.1): empréstimos atrasados ---------------------------------------

def consulta_atrasados(referencia: date, limite: int):
    return (
        select(
            Emprestimo.id,
            Emprestimo.data_emprestimo,
            Emprestimo.data_prevista,
            Livro.id.label("livro_id"),
            Livro.titulo,
            Leitor.id.label("leitor_id"),
            Leitor.nome,
        )
        .join(Livro, Livro.id == Emprestimo.livro_id)
        .join(Leitor, Leitor.id == Emprestimo.leitor_id)
        .where(Emprestimo.data_devolucao.is_(None), Emprestimo.data_prevista < referencia)
        .order_by(Emprestimo.data_prevista, Emprestimo.id)
        .limit(limite)
    )


@rotas.get("/atrasados", response_model=list[EmprestimoAtrasado], summary="Empréstimos atrasados")
def atrasados(
    data: Annotated[date | None, Query(description="Data de referência (padrão: hoje).")] = None,
    limite: Annotated[int, Query(ge=1, le=1000)] = 50,
):
    """Empréstimos em aberto com o prazo de devolução vencido, dos mais atrasados aos menos."""
    referencia = data or date.today()
    with Sessao() as sessao:
        linhas = sessao.execute(consulta_atrasados(referencia, limite)).all()
    return RespostaJSON([
        {
            "id": l.id,
            "data_emprestimo": l.data_emprestimo,
            "data_prevista": l.data_prevista,
            "dias_de_atraso": (referencia - l.data_prevista).days,
            "livro": {"id": l.livro_id, "titulo": l.titulo},
            "leitor": {"id": l.leitor_id, "nome": l.nome},
        }
        for l in linhas
    ])


# Operações de escrita -------------------------------------------------------------------------

@rotas.post("", status_code=201, response_model=EmprestimoRegistrado, summary="Registra um empréstimo")
def registrar_emprestimo(dados: NovoEmprestimo):
    """Bloqueia a linha do livro (SELECT ... FOR UPDATE), confere se há exemplar disponível e
    registra o empréstimo, com prazo de 14 dias."""
    with Sessao.begin() as sessao:
        livro = sessao.get(Livro, dados.livro_id, with_for_update=True)
        if livro is None:
            raise HTTPException(404, "Livro não encontrado.")
        if sessao.get(Leitor, dados.leitor_id) is None:
            raise HTTPException(404, "Leitor não encontrado.")
        if livro.exemplares_disponiveis == 0:
            raise HTTPException(409, "Nenhum exemplar disponível.")

        agora = datetime.now().replace(microsecond=0)
        emprestimo = Emprestimo(
            livro_id=livro.id,
            leitor_id=dados.leitor_id,
            data_emprestimo=agora,
            data_prevista=agora.date() + timedelta(days=14),
        )
        sessao.add(emprestimo)
        livro.exemplares_disponiveis -= 1
        sessao.flush()
        resposta = {**_resumido(emprestimo), "exemplares_disponiveis": livro.exemplares_disponiveis}
    return RespostaJSON(resposta, status_code=201)


@rotas.post(
    "/{emprestimo_id}/devolucao", response_model=EmprestimoRegistrado, summary="Registra a devolução"
)
def registrar_devolucao(emprestimo_id: Annotated[int, Path(gt=0)]):
    with Sessao.begin() as sessao:
        emprestimo = sessao.get(Emprestimo, emprestimo_id, with_for_update=True)
        if emprestimo is None:
            raise HTTPException(404, "Empréstimo não encontrado.")
        if emprestimo.data_devolucao is not None:
            raise HTTPException(409, "Este empréstimo já foi devolvido.")
        livro = sessao.get(Livro, emprestimo.livro_id, with_for_update=True)
        livro.exemplares_disponiveis += 1
        emprestimo.data_devolucao = datetime.now().replace(microsecond=0)
        resposta = {**_resumido(emprestimo), "exemplares_disponiveis": livro.exemplares_disponiveis}
    return RespostaJSON(resposta)

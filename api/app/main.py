"""Aplicação FastAPI: junta as rotas, o middleware de medição e o ciclo de vida."""

from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI

from . import config
from .banco import engine
from .medicao import MedirRequisicoes
from .rotas import emprestimos, laboratorio, leitores, livros


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # As rotas são síncronas e rodam num conjunto de threads. Há mais threads que conexões com o
    # banco: as requisições que precisam do banco esperam uma conexão livre dentro da thread, e as
    # que não precisam (acertos no cache) seguem sem entrar nessa fila.
    to_thread.current_default_thread_limiter().total_tokens = config.THREADS_POR_WORKER
    yield
    engine.dispose()


app = FastAPI(
    title="Biblioteca: otimização de Web Services",
    version="1.0.0",
    description=(
        "API REST de uma biblioteca, usada no Trabalho Prático A2 de Análise e Otimização de "
        "Sistemas. A mesma consulta existe em versões diferentes (sem e com cache; LAZY, EAGER e "
        "otimizada; sem e com índice) para comparar cada técnica por medição.\n\n"
        "Toda resposta traz `X-Consultas-SQL` (comandos SQL executados) e `Server-Timing` "
        "(tempo no banco e tempo total, em ms)."
    ),
    lifespan=ciclo_de_vida,
)
app.add_middleware(MedirRequisicoes)

app.include_router(livros.rotas)
app.include_router(emprestimos.rotas)
app.include_router(leitores.rotas)
app.include_router(laboratorio.rotas)


@app.get("/api/saude", tags=["Laboratório (preparo e observação dos experimentos)"], summary="A API está no ar?")
async def saude():
    return {"status": "ok"}

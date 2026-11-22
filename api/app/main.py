"""Aplicação FastAPI: junta as rotas, o middleware de medição e o ciclo de vida."""

from contextlib import asynccontextmanager
from pathlib import Path

import redis
from anyio import to_thread
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import cache, config
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


async def cache_fora_do_ar(request: Request, erro: Exception):
    """As rotas da biblioteca tratam a falha do Redis e buscam os dados no banco. Este tratador
    cobre as rotas de laboratório, que usam o Redis direto: 503 em vez de um 500 sem explicação."""
    if isinstance(erro, redis.RedisError):
        cache.registrar_falha(erro)
    return JSONResponse(
        status_code=503,
        content={"detail": "O cache (Redis) não respondeu. As rotas da biblioteca continuam no ar, "
                           "com os dados lidos do banco."},
    )


app.add_exception_handler(redis.RedisError, cache_fora_do_ar)
app.add_exception_handler(cache.CacheIndisponivel, cache_fora_do_ar)


@app.get("/api/saude", tags=["Laboratório (preparo e observação dos experimentos)"], summary="A API está no ar?")
async def saude():
    return {"status": "ok"}


# Painel de demonstração: uma página estática (HTML, CSS e JavaScript, sem dependências) que chama as
# rotas acima e mostra os números de cada resposta. Não faz parte do enunciado; serve para apresentar.
app.mount("/painel", StaticFiles(directory=Path(__file__).parent / "painel", html=True), name="painel")


@app.get("/", include_in_schema=False)
async def inicio():
    return RedirectResponse("/painel/")

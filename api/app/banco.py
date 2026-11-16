"""Conexão com o PostgreSQL (SQLAlchemy + psycopg) e contagem dos comandos SQL."""

from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from . import config
from .medicao import Comando, medicao_atual

engine = create_engine(
    config.URL_BANCO,
    pool_size=config.CONEXOES_POR_WORKER,
    max_overflow=0,
)

# expire_on_commit=False: os objetos continuam legíveis depois do commit, sem nova consulta.
Sessao = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine, "before_cursor_execute")
def _antes_do_comando(conn, cursor, statement, parameters, context, executemany):
    conn.info["inicio_do_comando"] = perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _depois_do_comando(conn, cursor, statement, parameters, context, executemany):
    duracao = perf_counter() - conn.info.pop("inicio_do_comando")
    medicao = medicao_atual.get()
    if medicao is None:
        return
    medicao.consultas += 1
    medicao.tempo_banco += duracao
    if medicao.comandos is not None:
        medicao.comandos.append(Comando.de(statement, parameters, cursor, duracao))

"""Conexão com o PostgreSQL (SQLAlchemy + psycopg) e contagem dos comandos SQL.

O banco fica no Supabase, a uns 160 ms de ida e volta da API. Por isso há duas fábricas de sessão:

    Sessao          transação explícita (BEGIN ... COMMIT), usada nas operações que escrevem
    SessaoLeitura   modo autocommit, usada nas leituras

Numa transação, o driver manda o BEGIN e o COMMIT (ou ROLLBACK) em idas e voltas separadas: duas
viagens ao banco a mais por requisição, que com o banco longe custam mais que as próprias consultas
de uma leitura simples. Em autocommit cada comando vale por si e só os comandos da requisição vão
ao banco. Nas leituras isso não muda o resultado.
"""

from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from . import config
from .medicao import Comando, medicao_atual

engine = create_engine(
    config.URL_BANCO,
    pool_size=config.CONEXOES_POR_WORKER,
    max_overflow=0,
    pool_timeout=config.ESPERA_POR_CONEXAO_S,
    connect_args={
        # A conexão atravessa a internet e o NAT do Docker: pacotes de keepalive a cada 30 s
        # evitam que uma conexão parada no pool seja derrubada no caminho.
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
        "application_name": "biblioteca-api",
    },
)

# expire_on_commit=False: os objetos continuam legíveis depois do commit, sem nova consulta.
Sessao = sessionmaker(engine, expire_on_commit=False)
SessaoLeitura = sessionmaker(
    engine.execution_options(isolation_level="AUTOCOMMIT"), expire_on_commit=False
)


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

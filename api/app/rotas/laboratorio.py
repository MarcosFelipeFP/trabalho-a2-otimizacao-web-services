"""Rotas de laboratório: preparam e observam os experimentos (não fazem parte da biblioteca).

    GET    /api/laboratorio/estado                       volume de dados, índices, versões
    GET    /api/laboratorio/cache                        estatísticas do Redis
    DELETE /api/laboratorio/cache                        esvazia o cache
    GET    /api/laboratorio/cache/livros/{id}            a ficha está no cache? quanto falta do TTL?
    GET    /api/laboratorio/indices                      índices da tabela emprestimo
    PUT    /api/laboratorio/indices/{nome}               cria um índice do experimento
    DELETE /api/laboratorio/indices/{nome}               remove um índice do experimento
    POST   /api/laboratorio/indices/custo-de-escrita     tempo para inserir N linhas (com ROLLBACK)
    GET    /api/laboratorio/explain/historico            EXPLAIN ANALYZE do histórico do leitor
    GET    /api/laboratorio/explain/atrasados            EXPLAIN ANALYZE dos empréstimos atrasados
    GET    /api/laboratorio/sql/...                      comandos SQL que uma operação executa
    GET    /api/laboratorio/banco/estatisticas           contadores do PostgreSQL
    DELETE /api/laboratorio/banco/estatisticas           zera os contadores
    POST   /api/laboratorio/banco/aquecer                carrega as tabelas na memória (pg_prewarm)
    POST   /api/laboratorio/banco/manutencao             VACUUM e REINDEX depois dos testes de escrita

Os testes de carga do k6 usam estas rotas para deixar o cache e os índices no estado certo antes
de cada medição. Num sistema em produção, elas ficariam desligadas ou protegidas.
"""

import platform
from dataclasses import asdict
from datetime import date
from enum import Enum
from importlib.metadata import version
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import text

from .. import cache, config
from ..banco import Sessao, engine
from ..medicao import Medicao, medicao_atual
from ..respostas import RespostaJSON, para_json
from .emprestimos import ESTRATEGIAS, ESTRATEGIAS_RESUMO, consulta_atrasados
from .leitores import consulta_historico, montar_historico
from .livros import montar_ficha

rotas = APIRouter(prefix="/api/laboratorio", tags=["Laboratório (preparo e observação dos experimentos)"])


# Estado geral ---------------------------------------------------------------------------------

@rotas.get("/estado", summary="Volume de dados, índices, configuração e versões")
def estado():
    with engine.connect() as conn:
        tabelas = {
            nome: conn.execute(text(f"SELECT count(*) FROM {nome}")).scalar()
            for nome in ("categoria", "autor", "livro", "leitor", "emprestimo")
        }
        em_aberto = conn.execute(
            text("SELECT count(*) FROM emprestimo WHERE data_devolucao IS NULL")
        ).scalar()
        tamanho = conn.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        ).scalar()
        versao_banco = conn.execute(text("SHOW server_version")).scalar()
        indices = _indices_de_emprestimo(conn)
    return RespostaJSON({
        "tabelas": tabelas,
        "emprestimos_em_aberto": em_aberto,
        "tamanho_do_banco": tamanho,
        "indices_de_emprestimo": indices,
        "configuracao": {
            "cache_ttl_segundos": config.CACHE_TTL_SEGUNDOS,
            "workers": config.WORKERS,
            "conexoes_por_worker": config.CONEXOES_POR_WORKER,
        },
        "versoes": {
            "postgresql": versao_banco,
            "redis": cache.cliente.info("server")["redis_version"],
            "python": platform.python_version(),
            "bibliotecas_python": {
                pacote: version(pacote)
                for pacote in ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "redis", "orjson")
            },
        },
    })


# Cache ----------------------------------------------------------------------------------------

@rotas.get("/cache", summary="Estatísticas do cache (Redis)")
def estatisticas_do_cache():
    info = cache.cliente.info()
    acertos, falhas = info["keyspace_hits"], info["keyspace_misses"]
    return RespostaJSON({
        "chaves": cache.cliente.dbsize(),
        "acertos": acertos,
        "falhas": falhas,
        "taxa_de_acerto": round(acertos / (acertos + falhas), 4) if acertos + falhas else None,
        "chaves_expiradas_pelo_ttl": info["expired_keys"],
        "chaves_descartadas_por_falta_de_memoria": info["evicted_keys"],
        "memoria_usada": info["used_memory_human"],
        "ttl_configurado_segundos": config.CACHE_TTL_SEGUNDOS,
    })


@rotas.delete("/cache", summary="Esvazia o cache e zera as estatísticas")
def esvaziar_cache():
    chaves = cache.cliente.dbsize()
    cache.cliente.flushdb()
    cache.cliente.config_resetstat()
    return RespostaJSON({"chaves_removidas": chaves})


@rotas.get("/cache/livros/{livro_id}", summary="Situação da ficha de um livro no cache")
def ficha_no_cache(livro_id: Annotated[int, Path(gt=0)]):
    chave = cache.chave_do_livro(livro_id)
    ttl = cache.cliente.ttl(chave)  # -2: a chave não existe
    return RespostaJSON({
        "chave": chave,
        "no_cache": ttl != -2,
        "ttl_restante_segundos": ttl if ttl >= 0 else None,
        "ttl_configurado_segundos": config.CACHE_TTL_SEGUNDOS,
    })


# Índices do experimento -----------------------------------------------------------------------

# Os mesmos comandos estão em banco/experimentos/indices.sql, para execução manual.
INDICES = {
    "leitor-data": (
        "idx_emprestimo_leitor_data",
        "CREATE INDEX idx_emprestimo_leitor_data ON emprestimo (leitor_id, data_emprestimo DESC)",
    ),
    "leitor": (
        "idx_emprestimo_leitor",
        "CREATE INDEX idx_emprestimo_leitor ON emprestimo (leitor_id)",
    ),
    "em-aberto": (
        "idx_emprestimo_em_aberto",
        "CREATE INDEX idx_emprestimo_em_aberto ON emprestimo (data_prevista) WHERE data_devolucao IS NULL",
    ),
}
NomeDoIndice = Enum("NomeDoIndice", {nome: nome for nome in INDICES}, type=str)


def _indices_de_emprestimo(conn) -> list[dict]:
    linhas = conn.execute(text("""
        SELECT indexrelname AS nome, pg_get_indexdef(indexrelid) AS definicao,
               pg_relation_size(indexrelid) AS bytes
        FROM pg_stat_user_indexes
        WHERE relname = 'emprestimo'
        ORDER BY indexrelname
    """)).all()
    return [dict(linha._mapping) for linha in linhas]


@rotas.get("/indices", summary="Índices da tabela emprestimo")
def listar_indices():
    with engine.connect() as conn:
        return RespostaJSON(_indices_de_emprestimo(conn))


@rotas.put("/indices/{nome}", summary="Cria um índice do experimento")
def criar_indice(nome: NomeDoIndice):
    """`leitor-data`: (leitor_id, data_emprestimo DESC), o índice proposto para o histórico.
    `leitor`: só leitor_id, para comparar. `em-aberto`: índice parcial dos empréstimos em aberto."""
    indice, comando = INDICES[nome.value]
    with engine.begin() as conn:
        existia = conn.execute(text("SELECT to_regclass(:nome) IS NOT NULL"), {"nome": indice}).scalar()
        if not existia:
            conn.execute(text(comando))
        conn.execute(text("ANALYZE emprestimo"))
        indices = _indices_de_emprestimo(conn)
    return RespostaJSON({"indice": indice, "criado_agora": not existia, "indices_de_emprestimo": indices})


@rotas.post("/indices/custo-de-escrita", summary="Tempo para inserir N empréstimos (desfeito no fim)")
def custo_de_escrita(linhas: Annotated[int, Query(ge=100, le=200_000)] = 20_000):
    """Insere N empréstimos numa transação, mede o tempo e desfaz tudo (ROLLBACK). Comparado
    com e sem índices, mostra o custo que cada índice acrescenta às escritas."""
    with engine.connect() as conn:
        indices = _indices_de_emprestimo(conn)
        inicio = perf_counter()
        conn.execute(text("""
            INSERT INTO emprestimo (livro_id, leitor_id, data_emprestimo, data_prevista)
            SELECT 1 + (g * 7919) % 20000, 1 + (g * 7907) % 10000,
                   localtimestamp - make_interval(mins => g), current_date + 14
            FROM generate_series(1, :linhas) AS g
        """), {"linhas": linhas})
        duracao = perf_counter() - inicio
        conn.rollback()
    return RespostaJSON({
        "linhas": linhas,
        "duracao_ms": round(duracao * 1000, 1),
        "microssegundos_por_linha": round(duracao * 1e6 / linhas, 2),
        "indices": [i["nome"] for i in indices],
        "bytes_dos_indices": sum(i["bytes"] for i in indices),
    })


@rotas.delete("/indices/{nome}", summary="Remove um índice do experimento")
def remover_indice(nome: NomeDoIndice):
    indice, _ = INDICES[nome.value]
    with engine.begin() as conn:
        existia = conn.execute(text("SELECT to_regclass(:nome) IS NOT NULL"), {"nome": indice}).scalar()
        conn.execute(text(f"DROP INDEX IF EXISTS {indice}"))
        conn.execute(text("ANALYZE emprestimo"))
        indices = _indices_de_emprestimo(conn)
    return RespostaJSON({"indice": indice, "removido_agora": existia, "indices_de_emprestimo": indices})


# Planos de execução ---------------------------------------------------------------------------

def _percorrer(no, nivel=0):
    yield nivel, no
    for filho in no.get("Plans", ()):
        yield from _percorrer(filho, nivel + 1)


def _explicar(consulta, random_page_cost: float | None = None) -> dict:
    """Executa a consulta uma vez (para aquecer) e depois com EXPLAIN ANALYZE.

    random_page_cost é o custo que o planejador atribui a ler uma página fora de ordem (padrão
    4, pensado para disco magnético). Ele pode ser trocado só nesta transação, para mostrar
    como o plano escolhido depende do modelo de custos."""
    compilada = consulta.compile(dialect=engine.dialect)
    sql, parametros = str(compilada), compilada.params
    with engine.connect() as conn:
        if random_page_cost is not None:
            conn.execute(
                text("SELECT set_config('random_page_cost', :valor, true)"),
                {"valor": str(random_page_cost)},
            )
        conn.exec_driver_sql(sql, parametros).all()
        texto = [linha for (linha,) in conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + sql, parametros)]
        [plano] = conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, parametros).scalar()
        indices = _indices_de_emprestimo(conn)

    operacoes = []
    for nivel, no in _percorrer(plano["Plan"]):
        lacos = no.get("Actual Loops", 1)
        operacoes.append({
            "nivel": nivel,
            "operacao": ("Parallel " if no.get("Parallel Aware") else "") + no["Node Type"],
            "tabela": no.get("Relation Name"),
            "indice": no.get("Index Name"),
            "linhas": round(no["Actual Rows"] * lacos),
            "lacos": lacos,
            "linhas_descartadas_pelo_filtro": round(no.get("Rows Removed by Filter", 0) * lacos),
            "ordenacao": no.get("Sort Key"),
            "blocos_em_memoria": no.get("Shared Hit Blocks"),
            "blocos_do_disco": no.get("Shared Read Blocks"),
        })
    return {
        "sql": sql,
        "parametros": parametros,
        "random_page_cost": random_page_cost if random_page_cost is not None else "padrão (4)",
        "indices_existentes": [i["nome"] for i in indices],
        "tempo_de_execucao_ms": plano["Execution Time"],
        "tempo_de_planejamento_ms": plano["Planning Time"],
        "indices_usados": sorted({o["indice"] for o in operacoes if o["indice"]}),
        "tabelas_lidas_por_inteiro": sorted({o["tabela"] for o in operacoes if o["operacao"].endswith("Seq Scan")}),
        "tem_ordenacao": any(o["operacao"] in ("Sort", "Incremental Sort") for o in operacoes),
        "operacoes": operacoes,
        "plano": texto,
    }


RandomPageCost = Annotated[
    float | None, Query(gt=0, le=10, description="Só para este EXPLAIN. Padrão do banco: 4.")
]


@rotas.get("/explain/historico", summary="EXPLAIN ANALYZE do histórico de um leitor")
def explain_historico(
    leitor_id: Annotated[int, Query(gt=0)] = 150,
    limite: Annotated[int | None, Query(ge=1, le=1000)] = None,
    random_page_cost: RandomPageCost = None,
):
    return RespostaJSON(_explicar(consulta_historico(leitor_id, limite), random_page_cost))


@rotas.get("/explain/atrasados", summary="EXPLAIN ANALYZE dos empréstimos atrasados")
def explain_atrasados(
    data: Annotated[date | None, Query(description="Padrão: hoje.")] = None,
    limite: Annotated[int, Query(ge=1, le=1000)] = 50,
    random_page_cost: RandomPageCost = None,
):
    return RespostaJSON(_explicar(consulta_atrasados(data or date.today(), limite), random_page_cost))


# SQL executado por uma operação ---------------------------------------------------------------

def _capturar(funcao, *argumentos) -> dict:
    """Executa a operação registrando cada comando SQL, com linhas e bytes devolvidos."""
    medicao = Medicao(comandos=[])
    token = medicao_atual.set(medicao)
    try:
        with Sessao() as sessao:
            resultado = funcao(sessao, *argumentos)
    finally:
        medicao_atual.reset(token)
    if resultado is None:
        raise HTTPException(404, "Registro não encontrado.")
    return {
        "consultas": len(medicao.comandos),
        "linhas_lidas_do_banco": sum(c.linhas for c in medicao.comandos),
        "bytes_lidos_do_banco": sum(c.bytes for c in medicao.comandos),
        "tempo_no_banco_ms": round(medicao.tempo_banco * 1000, 3),
        "itens_na_resposta": len(resultado) if isinstance(resultado, list) else None,
        "bytes_da_resposta": len(para_json(resultado)),
        "comandos": [asdict(c) for c in medicao.comandos],
    }


Estrategia = Enum("Estrategia", {nome: nome for nome in ESTRATEGIAS}, type=str)
EstrategiaDoResumo = Enum("EstrategiaDoResumo", {nome: nome for nome in ESTRATEGIAS_RESUMO}, type=str)
DesdeId = Annotated[int, Query(ge=1)]
Quantidade = Annotated[int, Query(ge=1, le=1000)]


@rotas.get("/sql/emprestimos/{estrategia}", summary="SQL da listagem de empréstimos")
def sql_emprestimos(estrategia: Estrategia, desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    return RespostaJSON(_capturar(ESTRATEGIAS[estrategia.value], desde_id, quantidade))


@rotas.get("/sql/emprestimos/{estrategia}/resumo", summary="SQL da listagem resumida")
def sql_resumo(estrategia: EstrategiaDoResumo, desde_id: DesdeId = 1, quantidade: Quantidade = 20):
    return RespostaJSON(_capturar(ESTRATEGIAS_RESUMO[estrategia.value], desde_id, quantidade))


@rotas.get("/sql/livros/{livro_id}/ficha", summary="SQL da ficha do livro (sem cache)")
def sql_ficha(livro_id: Annotated[int, Path(gt=0)]):
    return RespostaJSON(_capturar(montar_ficha, livro_id))


@rotas.get("/sql/leitores/{leitor_id}/emprestimos", summary="SQL do histórico do leitor")
def sql_historico(
    leitor_id: Annotated[int, Path(gt=0)],
    limite: Annotated[int | None, Query(ge=1, le=1000)] = None,
):
    return RespostaJSON(_capturar(montar_historico, leitor_id, limite))


# Estatísticas do PostgreSQL -------------------------------------------------------------------

@rotas.get("/banco/estatisticas", summary="Contadores do banco e comandos mais custosos")
def estatisticas_do_banco(limite: Annotated[int, Query(ge=1, le=100)] = 10):
    with engine.connect() as conn:
        banco = conn.execute(text("""
            SELECT xact_commit AS transacoes, blks_hit AS blocos_em_memoria,
                   blks_read AS blocos_do_disco, tup_returned AS linhas_percorridas,
                   tup_fetched AS linhas_buscadas, tup_inserted AS linhas_inseridas,
                   tup_updated AS linhas_alteradas, temp_bytes AS bytes_temporarios
            FROM pg_stat_database
            WHERE datname = current_database()
        """)).one()
        comandos = conn.execute(text("""
            SELECT calls AS execucoes, round(total_exec_time::numeric, 3) AS tempo_total_ms,
                   round(mean_exec_time::numeric, 4) AS tempo_medio_ms, rows AS linhas,
                   shared_blks_hit AS blocos_em_memoria,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 400) AS comando
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT :limite
        """), {"limite": limite}).all()
    return RespostaJSON({
        "banco": dict(banco._mapping),
        "comandos": [
            {**dict(c._mapping), "tempo_total_ms": float(c.tempo_total_ms), "tempo_medio_ms": float(c.tempo_medio_ms)}
            for c in comandos
        ],
    })


@rotas.delete("/banco/estatisticas", summary="Zera os contadores do banco")
def zerar_estatisticas_do_banco():
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_stat_reset()"))
        conn.execute(text("SELECT pg_stat_statements_reset()"))
        conn.commit()
    return RespostaJSON({"zerado": True})


@rotas.post("/banco/manutencao", summary="VACUUM ANALYZE e REINDEX da tabela emprestimo")
def manutencao():
    """Limpa as linhas mortas que os testes de escrita (desfeitos com ROLLBACK) deixam na tabela e
    nos índices, e reconstrói os índices, devolvendo a tabela ao tamanho original."""
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")  # VACUUM não roda em transação
        conn.execute(text("VACUUM (ANALYZE) emprestimo"))
        conn.execute(text("REINDEX TABLE emprestimo"))
        tamanho = conn.execute(text("SELECT pg_relation_size('emprestimo')")).scalar()
        indices = _indices_de_emprestimo(conn)
    return RespostaJSON({"bytes_da_tabela": tamanho, "indices_de_emprestimo": indices})


@rotas.post("/banco/aquecer", summary="Carrega tabelas e índices na memória do banco")
def aquecer_banco():
    """pg_prewarm em todas as tabelas e índices: as medições não dependem de quais páginas já
    tinham sido lidas do disco antes."""
    with engine.connect() as conn:
        blocos = conn.execute(text("""
            SELECT coalesce(sum(pg_prewarm(c.oid)), 0)::bigint
            FROM pg_class c
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'i')
        """)).scalar()
        conn.commit()
    return RespostaJSON({"blocos_carregados": blocos, "megabytes": round(blocos * 8 / 1024, 1)})

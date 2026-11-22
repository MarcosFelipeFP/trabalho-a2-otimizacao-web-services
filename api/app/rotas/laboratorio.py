"""Rotas de laboratório: preparam e observam os experimentos (não fazem parte da biblioteca).

    GET    /api/laboratorio/estado                       volume de dados, índices, versões
    GET    /api/laboratorio/cache                        estatísticas do Redis
    DELETE /api/laboratorio/cache                        esvazia o cache
    GET    /api/laboratorio/cache/livros/{id}            a ficha está no cache? quanto falta do TTL?
    PUT    /api/laboratorio/cache/livros/{id}/ttl        encurta o TTL de uma ficha (demonstração da expiração)
    POST   /api/laboratorio/cache/encher                 guarda as fichas de todos os livros (cache quente)
    POST   /api/laboratorio/cache/pausar                 trava o Redis por alguns segundos (Redis fora do ar)
    GET    /api/laboratorio/indices                      índices da tabela emprestimo
    PUT    /api/laboratorio/indices/{nome}               cria um índice do experimento
    DELETE /api/laboratorio/indices/{nome}               remove um índice do experimento
    POST   /api/laboratorio/indices/custo-de-escrita     tempo para inserir N linhas (com ROLLBACK)
    GET    /api/laboratorio/explain/historico            EXPLAIN ANALYZE do histórico do leitor
    GET    /api/laboratorio/explain/atrasados            EXPLAIN ANALYZE dos empréstimos atrasados
    GET    /api/laboratorio/sql/...                      comandos SQL que uma operação executa
    GET    /api/laboratorio/banco/estatisticas           comandos da API no banco (pg_stat_statements)
    DELETE /api/laboratorio/banco/estatisticas           zera esses contadores, se o banco permitir
    GET    /api/laboratorio/banco/ida-e-volta            tempo de uma ida e volta ao banco (SELECT 1)
    POST   /api/laboratorio/banco/aquecer                carrega as tabelas na memória (pg_prewarm)
    POST   /api/laboratorio/banco/manutencao             VACUUM e REINDEX depois dos testes de escrita
    PUT    /api/laboratorio/banco/livros/{id}/titulo     altera o título direto no banco, sem avisar o cache

Os testes de carga do k6 usam estas rotas para deixar o cache e os índices no estado certo antes
de cada medição. Num sistema em produção, elas ficariam desligadas ou protegidas.

As rotas do cache usam o Redis direto: se ele não responder, elas devolvem 503 (tratador em
main.py), enquanto as rotas da biblioteca continuam respondendo com os dados do banco.
"""

import platform
import statistics
from dataclasses import asdict
from datetime import date
from enum import Enum
from importlib.metadata import version
from time import perf_counter
from typing import Annotated

import redis
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .. import cache, config
from ..banco import SessaoLeitura, engine
from ..medicao import Medicao, medicao_atual
from ..respostas import RespostaJSON, para_json
from .emprestimos import ESTRATEGIAS, ESTRATEGIAS_RESUMO, consulta_atrasados
from .leitores import consulta_historico, montar_historico
from .livros import montar_ficha, montar_fichas

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
        # Só as tabelas da biblioteca: no Supabase o banco também guarda as tabelas do projeto.
        tamanho = conn.execute(text("""
            SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid)))
            FROM pg_class c
            WHERE c.relname IN ('categoria', 'autor', 'livro', 'leitor', 'emprestimo')
              AND c.relnamespace = 'public'::regnamespace
        """)).scalar()
        servidor = conn.execute(text("""
            SELECT current_setting('server_version') AS versao,
                   current_setting('max_connections') AS max_connections,
                   current_setting('shared_buffers') AS shared_buffers,
                   current_setting('work_mem') AS work_mem,
                   current_setting('random_page_cost') AS random_page_cost,
                   current_setting('max_parallel_workers_per_gather') AS max_parallel_workers_per_gather,
                   current_user AS usuario
        """)).one()
        indices = _indices_de_emprestimo(conn)
    return RespostaJSON({
        "tabelas": tabelas,
        "emprestimos_em_aberto": em_aberto,
        "tamanho_do_banco": tamanho,
        "indices_de_emprestimo": indices,
        "banco": {"servidor": config.SERVIDOR_DO_BANCO, **dict(servidor._mapping)},
        "configuracao": {
            "cache_ttl_segundos": config.CACHE_TTL_SEGUNDOS,
            "cache_tempo_limite_s": config.CACHE_TEMPO_LIMITE_S,
            "cache_intervalo_da_vigia_s": cache.INTERVALO_DA_VIGIA_S,
            "workers": config.WORKERS,
            "conexoes_por_worker": config.CONEXOES_POR_WORKER,
            "threads_por_worker": config.THREADS_POR_WORKER,
        },
        "versoes": {
            "postgresql": servidor.versao,
            "redis": cache.versao(),  # None: o Redis não respondeu (o resto continua valendo)
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


@rotas.post("/cache/encher", summary="Guarda no cache as fichas de todos os livros")
def encher_cache():
    """Prepara o cenário de cache quente dos testes de carga. Monta as 20.000 fichas com duas
    consultas (montar_fichas) e as grava no Redis de uma vez, com o TTL configurado. Passar por
    GET /com-cache livro a livro faria 60.000 consultas; com o banco a 160 ms, uns 15 minutos."""
    inicio = perf_counter()
    with SessaoLeitura() as sessao:
        fichas = montar_fichas(sessao)
    montadas = perf_counter()
    tubo = cache.cliente.pipeline(transaction=False)
    for ficha in fichas:
        tubo.set(cache.chave_do_livro(ficha["id"]), para_json(ficha), ex=config.CACHE_TTL_SEGUNDOS)
    tubo.execute()
    return RespostaJSON({
        "fichas_guardadas": len(fichas),
        "chaves_no_cache": cache.cliente.dbsize(),
        "montagem_ms": round((montadas - inicio) * 1000),
        "gravacao_no_redis_ms": round((perf_counter() - montadas) * 1000),
        "ttl_segundos": config.CACHE_TTL_SEGUNDOS,
    })


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


@rotas.put("/cache/livros/{livro_id}/ttl", summary="Encurta o tempo de vida de uma ficha no cache")
def encurtar_ttl(
    livro_id: Annotated[int, Path(gt=0)],
    segundos: Annotated[int, Query(ge=1, le=config.CACHE_TTL_SEGUNDOS)] = 15,
):
    """Para a expiração caber numa demonstração: troca o TTL só desta ficha (EXPIRE no Redis),
    sem recriar a API com outro CACHE_TTL_SEGUNDOS. Quando o tempo acaba, o Redis apaga a ficha e
    a próxima leitura com cache é uma falha (MISS), que busca a versão atual no banco."""
    chave = cache.chave_do_livro(livro_id)
    if not cache.cliente.expire(chave, segundos):
        raise HTTPException(404, "A ficha deste livro não está no cache: leia com cache antes.")
    return RespostaJSON({
        "chave": chave,
        "no_cache": True,
        "ttl_restante_segundos": cache.cliente.ttl(chave),
        "ttl_configurado_segundos": config.CACHE_TTL_SEGUNDOS,
    })


@rotas.post("/cache/pausar", summary="Trava o Redis por alguns segundos (Redis fora do ar)")
def pausar_o_redis(segundos: Annotated[int, Query(ge=1, le=60)] = 15):
    """Simula um Redis que parou de responder, sem precisar do Docker: `CLIENT PAUSE` faz o Redis
    segurar os comandos de todos os clientes, de todos os processos da API, até o tempo acabar. Os
    dados continuam lá. Enquanto isso, a ficha com cache vem do banco (`X-Cache: INDISPONIVEL`) e
    uma alteração pelo PUT deixa a invalidação pendente; quando o Redis volta, a invalidação é
    feita antes de o cache voltar a ser usado.

    Serve para a demonstração no painel: nos testes, a pausa às vezes terminou antes do tempo
    pedido. Para medir, experimentos/falha_do_cache.py congela o contêiner (docker compose pause)."""
    cache.cliente.client_pause(segundos * 1000, all=True)
    return RespostaJSON({
        "redis_travado_por_segundos": segundos,
        "tempo_limite_da_api_s": config.CACHE_TEMPO_LIMITE_S,
        "intervalo_da_vigia_s": cache.INTERVALO_DA_VIGIA_S,
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
    com e sem índices, mostra o custo que cada índice acrescenta às escritas.

    O tempo é o de execução no próprio banco (EXPLAIN ANALYZE, que executa o INSERT de verdade,
    inclusive a conferência das chaves estrangeiras), sem a ida e volta pela rede. TIMING OFF
    dispensa a cronometragem de cada etapa do plano, que pesaria numa operação com 20.000 linhas."""
    with engine.connect() as conn:
        indices = _indices_de_emprestimo(conn)
        inicio = perf_counter()
        [plano] = conn.execute(text("""
            EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON)
            INSERT INTO emprestimo (livro_id, leitor_id, data_emprestimo, data_prevista)
            SELECT 1 + (g * 7919) % 20000, 1 + (g * 7907) % 10000,
                   localtimestamp - make_interval(mins => g), current_date + 14
            FROM generate_series(1, :linhas) AS g
        """), {"linhas": linhas}).scalar()
        no_cliente = perf_counter() - inicio
        conn.rollback()
    execucao_ms = plano["Execution Time"]
    return RespostaJSON({
        "linhas": linhas,
        "duracao_ms": round(execucao_ms, 1),
        "microssegundos_por_linha": round(execucao_ms * 1000 / linhas, 2),
        "duracao_vista_pela_api_ms": round(no_cliente * 1000, 1),
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

    random_page_cost é o custo que o planejador atribui a ler uma página fora de ordem. O padrão
    do PostgreSQL é 4, pensado para disco magnético; o Supabase usa 1,1, valor indicado para SSD.
    Ele pode ser trocado só nesta transação, para mostrar como o plano escolhido depende do
    modelo de custos."""
    compilada = consulta.compile(dialect=engine.dialect)
    sql, parametros = str(compilada), compilada.params
    with engine.connect() as conn:
        if random_page_cost is not None:
            conn.execute(
                text("SELECT set_config('random_page_cost', :valor, true)"),
                {"valor": str(random_page_cost)},
            )
        custo_em_uso = conn.execute(text("SELECT current_setting('random_page_cost')")).scalar()
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
        "random_page_cost": custo_em_uso + (" (padrão do banco)" if random_page_cost is None else ""),
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
    float | None,
    Query(gt=0, le=10, description="Só para este EXPLAIN. Padrão do PostgreSQL: 4; do Supabase: 1,1."),
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
        with SessaoLeitura() as sessao:  # como nas rotas de leitura: sem BEGIN e COMMIT
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

# Comandos do usuário da API nas tabelas da biblioteca. No Supabase o mesmo banco também recebe as
# consultas dos serviços do projeto (autenticação, armazenamento, painel), que ficam de fora. O que
# alguém rodar nessas tabelas pelo painel, que também usa o usuário postgres, entraria na conta: por
# isso nada é feito no painel durante as medições.
_DA_BIBLIOTECA = r"""
    userid = (SELECT oid FROM pg_roles WHERE rolname = current_user)
    AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
    AND query ~* '^\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\M'
    AND query ~* '\m(emprestimo|livro|leitor|autor|categoria)\M'
    AND query !~* 'pg_stat_statements|pg_prewarm|pg_class|pg_index|pg_roles'
"""


@rotas.get("/banco/estatisticas", summary="Comandos da API no banco (pg_stat_statements)")
def estatisticas_do_banco(limite: Annotated[int, Query(ge=1, le=1000)] = 10):
    """Contadores acumulados (pg_stat_statements) dos comandos que o usuário da API executou nas
    tabelas da biblioteca: o total e os `limite` comandos de maior tempo. Para medir um intervalo,
    leia antes e depois e subtraia; o roteiro dos testes de carga faz assim."""
    with engine.connect() as conn:
        total = conn.execute(text(f"""
            SELECT coalesce(sum(calls), 0)::bigint AS execucoes,
                   coalesce(sum(total_exec_time), 0)::float8 AS tempo_total_ms,
                   coalesce(sum(rows), 0)::bigint AS linhas,
                   coalesce(sum(shared_blks_hit), 0)::bigint AS blocos_em_memoria,
                   coalesce(sum(shared_blks_read), 0)::bigint AS blocos_do_disco
            FROM pg_stat_statements
            WHERE {_DA_BIBLIOTECA}
        """)).one()
        comandos = conn.execute(text(rf"""
            SELECT queryid::text AS id, calls AS execucoes, total_exec_time AS tempo_total_ms,
                   rows AS linhas, shared_blks_hit AS blocos_em_memoria,
                   shared_blks_read AS blocos_do_disco,
                   left(regexp_replace(query, '\s+', ' ', 'g'), 400) AS comando
            FROM pg_stat_statements
            WHERE {_DA_BIBLIOTECA}
            ORDER BY total_exec_time DESC
            LIMIT :limite
        """), {"limite": limite}).all()
    return RespostaJSON({
        "total": dict(total._mapping),
        "comandos": [dict(c._mapping) for c in comandos],
    })


@rotas.delete("/banco/estatisticas", summary="Zera as estatísticas dos comandos da API, se permitido")
def zerar_estatisticas_do_banco():
    """Zera pg_stat_statements para o usuário da API (no Supabase, o postgres tem essa permissão).
    Se o banco não permitir, a resposta diz o motivo. As medições não dependem disso: usam a
    diferença entre duas leituras (GET)."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "SELECT pg_stat_statements_reset((SELECT oid FROM pg_roles WHERE rolname = current_user))"
            ))
            conn.commit()
    except DBAPIError as erro:
        return RespostaJSON({"zerado": False, "motivo": str(erro.orig).strip()})
    return RespostaJSON({"zerado": True})


@rotas.get("/banco/ida-e-volta", summary="Tempo de uma ida e volta ao banco (SELECT 1)")
def ida_e_volta(vezes: Annotated[int, Query(ge=1, le=200)] = 20):
    """Executa SELECT 1 várias vezes, na mesma conexão, e mede cada uma: é o custo fixo que toda
    consulta paga além do trabalho do banco. Com o banco no Supabase, é quase todo rede."""
    tempos = []
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql("SELECT 1").scalar()  # a primeira pode abrir a conexão
        for _ in range(vezes):
            inicio = perf_counter()
            conn.exec_driver_sql("SELECT 1").scalar()
            tempos.append((perf_counter() - inicio) * 1000)
    tempos.sort()
    return RespostaJSON({
        "vezes": vezes,
        "servidor_do_banco": config.SERVIDOR_DO_BANCO,
        "mediana_ms": round(statistics.median(tempos), 2),
        "minimo_ms": round(tempos[0], 2),
        "p90_ms": round(tempos[min(len(tempos) - 1, int(len(tempos) * 0.9))], 2),
        "maximo_ms": round(tempos[-1], 2),
    })


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
    """pg_prewarm nas tabelas da biblioteca e nos índices delas (as que pertencem ao usuário da
    API): as medições não dependem de quais páginas já tinham sido lidas do disco antes."""
    with engine.connect() as conn:
        blocos = conn.execute(text("""
            SELECT coalesce(sum(pg_prewarm(c.oid)), 0)::bigint
            FROM pg_class c
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'i')
              AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
        """)).scalar()
        conn.commit()
    return RespostaJSON({"blocos_carregados": blocos, "megabytes": round(blocos * 8 / 1024, 1)})


class TituloNoBanco(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)


@rotas.put("/banco/livros/{livro_id}/titulo", summary="Altera o título direto no banco, sem avisar o cache")
def alterar_titulo_por_fora_da_api(livro_id: Annotated[int, Path(gt=0)], dados: TituloNoBanco):
    """Simula uma alteração feita por fora da API (um comando SQL direto no banco, uma importação):
    o UPDATE não passa pela rota PUT /api/livros/{id}, que apaga a ficha do cache. Se a ficha
    estiver no cache, ela continua sendo servida, desatualizada, até o TTL acabar. É o passo 5 do
    experimento da seção 3.4, que experimentos/cache.py faz com o psql."""
    with engine.begin() as conn:
        alteradas = conn.execute(
            text("UPDATE livro SET titulo = :titulo WHERE id = :id"),
            {"titulo": dados.titulo, "id": livro_id},
        ).rowcount
    if not alteradas:
        raise HTTPException(404, "Livro não encontrado.")
    try:
        ttl = cache.cliente.ttl(cache.chave_do_livro(livro_id))  # -2: a chave não existe
    except redis.RedisError as erro:
        # o UPDATE já foi feito; só não dá para dizer se a ficha está no cache
        cache.registrar_falha(erro)
        ttl = None
    return RespostaJSON({
        "livro_id": livro_id,
        "titulo_no_banco": dados.titulo,
        "cache_avisado": False,
        "ficha_no_cache": None if ttl is None else ttl != -2,
        "ttl_restante_segundos": ttl if ttl is not None and ttl >= 0 else None,
    })

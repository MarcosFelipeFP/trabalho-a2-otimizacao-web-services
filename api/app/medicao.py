"""Medição de cada requisição: quantos comandos SQL ela executou e quanto tempo eles levaram.

Toda resposta da API sai com dois cabeçalhos:

    X-Consultas-SQL: 41
    Server-Timing: banco;dur=6.12, total;dur=9.87     (milissegundos)

Assim o número de consultas de cada estratégia (LAZY, EAGER, otimizada...) pode ser observado
em qualquer requisição, inclusive pelo k6 durante os testes de carga.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter


@dataclass(slots=True)
class Comando:
    """Um comando SQL executado, com o volume de dados que voltou do banco."""

    sql: str
    parametros: object
    linhas: int
    colunas: int
    bytes: int
    duracao_ms: float

    @classmethod
    def de(cls, sql, parametros, cursor, duracao):
        linhas, colunas, tamanho = _volume_do_resultado(cursor)
        return cls(sql, parametros, linhas, colunas, tamanho, round(duracao * 1000, 3))


@dataclass(slots=True)
class Medicao:
    consultas: int = 0
    tempo_banco: float = 0.0  # segundos
    # Lista dos comandos, só quando a captura é pedida (rotas /api/laboratorio/sql/...).
    comandos: list[Comando] | None = None


# Medição da requisição em andamento. As rotas síncronas rodam em threads separadas, mas o
# FastAPI copia o contexto para a thread, então todas enxergam o mesmo objeto.
medicao_atual: ContextVar[Medicao | None] = ContextVar("medicao_atual", default=None)


def _volume_do_resultado(cursor):
    """Linhas, colunas e bytes (no formato texto do PostgreSQL) devolvidos pelo comando."""
    resultado = getattr(cursor, "pgresult", None)
    if resultado is None:
        return 0, 0, 0
    linhas, colunas = resultado.ntuples, resultado.nfields
    tamanho = sum(
        len(resultado.get_value(i, j) or b"") for i in range(linhas) for j in range(colunas)
    )
    return linhas, colunas, tamanho


class MedirRequisicoes:
    """Middleware ASGI que abre uma medição por requisição e escreve os cabeçalhos."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        medicao = Medicao()
        token = medicao_atual.set(medicao)
        inicio = perf_counter()

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                total_ms = (perf_counter() - inicio) * 1000
                cabecalhos = list(mensagem.get("headers", ()))
                cabecalhos.append((b"x-consultas-sql", str(medicao.consultas).encode()))
                cabecalhos.append((
                    b"server-timing",
                    f"banco;dur={medicao.tempo_banco * 1000:.2f}, total;dur={total_ms:.2f}".encode(),
                ))
                mensagem = {**mensagem, "headers": cabecalhos}
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        finally:
            medicao_atual.reset(token)

"""Cache das fichas de livro no Redis.

Estratégia cache-aside: a rota procura a ficha no Redis; se não acha, monta a ficha a partir do
banco e grava no Redis com tempo de vida (TTL). Quando a ficha muda pela API, a chave é apagada
(invalidação) e a próxima leitura busca a versão nova no banco.

O Redis fica fora da API e é compartilhado pelos processos dela: invalidar uma chave vale para
todos os processos ao mesmo tempo. Um cache dentro de cada processo exigiria avisar os outros.
"""

import redis

from . import config

cliente = redis.Redis.from_url(config.URL_CACHE)


def chave_do_livro(livro_id: int) -> str:
    return f"livro:{livro_id}"


def ler(chave: str) -> bytes | None:
    return cliente.get(chave)


def gravar(chave: str, valor: bytes, ttl_segundos: int = config.CACHE_TTL_SEGUNDOS) -> None:
    cliente.set(chave, valor, ex=ttl_segundos)


def invalidar(chave: str) -> bool:
    """Apaga a chave; devolve True se ela estava no cache."""
    return cliente.delete(chave) > 0

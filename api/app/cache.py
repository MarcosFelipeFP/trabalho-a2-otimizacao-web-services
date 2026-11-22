"""Cache das fichas de livro no Redis.

Estratégia cache-aside: a rota procura a ficha no Redis; se não acha, monta a ficha a partir do
banco e grava no Redis com tempo de vida (TTL). Quando a ficha muda pela API, a chave é apagada
(invalidação) e a próxima leitura busca a versão nova no banco.

O Redis fica fora da API e é compartilhado pelos processos dela: invalidar uma chave vale para
todos os processos ao mesmo tempo. Um cache dentro de cada processo exigiria avisar os outros.

O cache é um atalho, não a fonte dos dados. Se o Redis não responder, ler, gravar e invalidar
levantam CacheIndisponivel e a rota busca a ficha no banco. Depois da primeira falha, o processo
para de tentar o Redis nas requisições: uma vigia, em segundo plano, testa o Redis a cada segundo
e só devolve o cache às requisições quando ele responde. Uma invalidação que falhou fica pendente,
e a vigia a faz antes de o cache voltar a ser usado; sem isso, um Redis que volta com os dados de
antes (travado, e não reiniciado) serviria a ficha antiga até o TTL acabar.
"""

import logging
import os
import threading
import time

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from . import config

# Sem novas tentativas: se o Redis falhou, a requisição vai ao banco em vez de esperar por ele de
# novo. O tempo limite vale para abrir a conexão e para cada leitura ou escrita no socket, mas não
# cobre a resolução do nome "cache": com o contêiner parado, o DNS do Docker leva uns 3 s para
# responder que o nome não existe. Por isso quem testa o Redis depois de uma falha é a vigia, e
# não as requisições.
cliente = redis.Redis.from_url(
    config.URL_CACHE,
    socket_connect_timeout=config.CACHE_TEMPO_LIMITE_S,
    socket_timeout=config.CACHE_TEMPO_LIMITE_S,
    retry=Retry(NoBackoff(), 0),
)

INTERVALO_DA_VIGIA_S = 1.0

log = logging.getLogger("biblioteca.cache")


class CacheIndisponivel(Exception):
    """O Redis não respondeu, ou este processo está esperando ele voltar: use o banco."""


# Estado deste processo (cada processo da API tem o seu).
_trava = threading.Lock()
_disponivel = True
_vigiando = False       # há uma vigia rodando; vale sempre que _disponivel é False
_fora_desde = 0.0       # time.monotonic() da primeira falha
_pendentes: set[str] = set()  # chaves que deveriam ter sido apagadas e não foram


def chave_do_livro(livro_id: int) -> str:
    return f"livro:{livro_id}"


def ler(chave: str) -> bytes | None:
    """A ficha guardada, ou None se ela não está no cache."""
    _conferir()
    try:
        return cliente.get(chave)
    except redis.RedisError as erro:
        raise registrar_falha(erro) from erro


def gravar(chave: str, valor: bytes, ttl_segundos: int = config.CACHE_TTL_SEGUNDOS) -> None:
    _conferir()
    try:
        cliente.set(chave, valor, ex=ttl_segundos)
    except redis.RedisError as erro:
        raise registrar_falha(erro) from erro


def invalidar(chave: str) -> bool:
    """Apaga a chave; devolve True se ela estava no cache. Se o Redis não responder, a chave fica
    pendente (a vigia a apaga quando ele voltar) e levanta CacheIndisponivel."""
    with _trava:
        if not _disponivel:
            _pendentes.add(chave)
            raise CacheIndisponivel("invalidação pendente: o Redis está fora do ar")
    try:
        return cliente.delete(chave) > 0
    except redis.RedisError as erro:
        with _trava:
            _pendentes.add(chave)
        raise registrar_falha(erro) from erro


def versao() -> str | None:
    """Versão do servidor Redis, ou None se ele não está respondendo."""
    try:
        _conferir()
        return cliente.info("server")["redis_version"]
    except CacheIndisponivel:
        return None
    except redis.RedisError as erro:
        registrar_falha(erro)
        return None


def registrar_falha(erro: Exception) -> CacheIndisponivel:
    """Tira o Redis das requisições deste processo e põe a vigia para esperar ele voltar."""
    global _disponivel, _vigiando, _fora_desde
    with _trava:
        if _disponivel:
            _disponivel = False
            _fora_desde = time.monotonic()
            log.warning("Processo %d: o Redis não respondeu (%s); as fichas vêm do banco até ele voltar.",
                        os.getpid(), erro)
        if not _vigiando:
            _vigiando = True
            threading.Thread(target=_vigiar, name="vigia-do-cache", daemon=True).start()
    return CacheIndisponivel(str(erro))


def _conferir() -> None:
    if not _disponivel:
        raise CacheIndisponivel("o Redis está fora do ar")


def _vigiar() -> None:
    """Testa o Redis a cada INTERVALO_DA_VIGIA_S. Quando ele responde, apaga as chaves pendentes e
    só então devolve o cache às requisições deste processo."""
    global _disponivel, _vigiando
    feitas = 0
    while True:
        time.sleep(INTERVALO_DA_VIGIA_S)
        with _trava:
            pendentes = list(_pendentes)
        try:
            cliente.ping()
            if pendentes:
                cliente.delete(*pendentes)
        except redis.RedisError:
            continue
        with _trava:
            _pendentes.difference_update(pendentes)
            feitas += len(pendentes)
            if _pendentes:
                continue  # outras invalidações falharam enquanto estas eram feitas
            _disponivel = True
            _vigiando = False
            fora = time.monotonic() - _fora_desde
        log.warning("Processo %d: o Redis respondeu de novo depois de %.1f s; %d invalidações pendentes feitas.",
                    os.getpid(), fora, feitas)
        return

"""Configuração da API, lida das variáveis de ambiente (ver docker-compose.yml)."""

import os

URL_BANCO = os.environ.get(
    "URL_BANCO", "postgresql+psycopg://biblioteca:biblioteca@localhost:5432/biblioteca"
)
URL_CACHE = os.environ.get("URL_CACHE", "redis://localhost:6379/0")

# Tempo de vida das fichas de livro no cache, em segundos.
CACHE_TTL_SEGUNDOS = int(os.environ.get("CACHE_TTL_SEGUNDOS", "600"))

# Conexões com o banco em cada processo da API. É também o número de requisições que cada
# processo atende ao mesmo tempo, para nenhuma ficar esperando conexão livre.
CONEXOES_POR_WORKER = int(os.environ.get("CONEXOES_POR_WORKER", "20"))

# Quantidade de processos da API. Quem cria os processos é o uvicorn (--workers); aqui o valor
# só é informado em /api/laboratorio/estado.
WORKERS = int(os.environ.get("WORKERS", "1"))

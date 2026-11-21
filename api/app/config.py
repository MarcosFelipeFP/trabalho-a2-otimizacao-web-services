"""Configuração da API, lida das variáveis de ambiente (ver docker-compose.yml e .env.exemplo)."""

import os

# Sem URL_BANCO, o driver (libpq) usa as variáveis padrão do PostgreSQL: PGHOST, PGPORT, PGUSER,
# PGPASSWORD, PGDATABASE e PGSSLMODE. É assim que a API chega ao Supabase sem guardar a senha
# numa URL.
URL_BANCO = os.environ.get("URL_BANCO", "postgresql+psycopg://")
URL_CACHE = os.environ.get("URL_CACHE", "redis://localhost:6379/0")

# Onde está o banco, só para registro em /api/laboratorio/estado.
SERVIDOR_DO_BANCO = os.environ.get("PGHOST", "localhost")

# Tempo de vida das fichas de livro no cache, em segundos.
CACHE_TTL_SEGUNDOS = int(os.environ.get("CACHE_TTL_SEGUNDOS", "600"))

# Conexões com o banco em cada processo da API. O pooler de sessões do Supabase aceita até 15
# conexões simultâneas por usuário; com 4 processos, 3 conexões em cada um.
CONEXOES_POR_WORKER = int(os.environ.get("CONEXOES_POR_WORKER", "3"))

# Requisições atendidas ao mesmo tempo por processo (threads). É maior que o número de conexões
# de propósito: uma requisição que não usa o banco (acerto no cache) não espera na fila das que
# estão esperando uma conexão livre.
THREADS_POR_WORKER = int(os.environ.get("THREADS_POR_WORKER", "40"))

# Quanto uma requisição pode esperar por uma conexão livre antes de falhar, em segundos. Longo de
# propósito: nos testes de carga quem desiste é o cliente (o k6 espera até 60 s).
ESPERA_POR_CONEXAO_S = int(os.environ.get("ESPERA_POR_CONEXAO_S", "600"))

# Quantidade de processos da API. Quem cria os processos é o uvicorn (--workers); aqui o valor
# só é informado em /api/laboratorio/estado.
WORKERS = int(os.environ.get("WORKERS", "1"))

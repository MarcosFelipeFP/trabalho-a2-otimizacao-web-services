# Resultados dos testes de desempenho

Gerado por `testes-carga/analisar.py` a partir das execuções do k6 desta pasta.

## Ambiente

- Data: 2026-11-22 15:45:36
- Máquina: AMD Ryzen 5 5600X 6-Core Processor, 12 núcleos lógicos, 23,9 GB; Windows-11-10.0.26200-SP0
- Docker: 29.7.2 | VM com 6 CPUs e 6214619136 bytes de memória
- k6: k6 v2.3.0 (commit/e088784614, go1.27.1, linux/amd64) (contêiner na rede da API)
- API: Python 3.14.10, 4 processos, 3 conexões por processo; fastapi 0.163.1, uvicorn 0.54.0, sqlalchemy 2.1.8, psycopg 3.3.9, redis 8.1.0, orjson 3.13.0
- Banco: PostgreSQL 17.12 em aws-1-us-east-2.pooler.supabase.com (165 MB nas tabelas da biblioteca; random_page_cost 1.1); cache: Redis 8.10.3
- Ida e volta da API até o banco (SELECT 1, 50 vezes): mediana 152,7 ms, mínimo 149,0 ms, máximo 305,6 ms
- Dados: categoria 20, autor 5.000, livro 20.000, leitor 10.000, emprestimo 300.000
- Cargas: 10,50,100,200 VUs; 10 s de aquecimento e 30 s de medição por nível; 3 repetições
- Outros contêineres em execução: petmotion-pc-worker-1 (petmotion:local), petmotion-pc-api-1 (petmotion:local)

## Comparação das versões com 50 VUs

| cenário | versão | latência média (ms) | p95 (ms) | p99 (ms) | vazão (req/s) | erros | SQL por req. |
|---|---|---:|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 2.000 | 2.392 | 3.802 | 25,7 | 0,00% | 3,0 |
| Cenário 1 | cache frio | 1.675 | 3.887 | 4.125 | 30,2 | 0,00% | 2,6 |
| Cenário 1 | cache quente | 7,28 | 15,1 | 20,8 | 6.764,9 | 0,00% | 0,0 |
| Cenário 2 | LAZY | 21.045 | 29.285 | 29.848 | 0,8 | 0,00% | 41,0 |
| Cenário 2 | EAGER | 703 | 1.100 | 1.418 | 72,1 | 0,00% | 1,0 |
| Cenário 2 | otimizada | 684 | 843 | 1.230 | 74,1 | 0,00% | 1,0 |
| Cenário 2 | SQL nativo | 693 | 882 | 1.177 | 73,4 | 0,00% | 1,0 |
| Cenário 3 | sem índice | 1.414 | 2.326 | 3.776 | 36,1 | 0,00% | 1,0 |
| Cenário 3 | com índice | 720 | 1.343 | 1.683 | 71,1 | 0,00% | 1,0 |

## Cenário 1: ficha do livro sem e com cache

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | acertos no cache | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem cache | 17 | 594 | 778 | 1.257 | 0,00% | – | 3,0 | 11% | 14% | ±18,0% |
| 10 | cache frio | 16 | 655 | 1.142 | 1.408 | 0,00% | 9% | 2,7 | 11% | 16% | ±24,7% |
| 10 | cache quente | 5.773 | 1,63 | 3,44 | 5,31 | 0,00% | 100% | 0,0 | 296% | 0% | ±11,3% |
| 50 | sem cache | 26 | 2.000 | 2.392 | 3.802 | 0,00% | – | 3,0 | 15% | 18% | ±1,9% |
| 50 | cache frio | 30 | 1.675 | 3.887 | 4.125 | 0,00% | 14% | 2,6 | 14% | 43% | ±4,0% |
| 50 | cache quente | 6.765 | 7,28 | 15,1 | 20,8 | 0,00% | 100% | 0,0 | 316% | 0% | ±8,9% |
| 100 | sem cache | 24 | 4.065 | 9.091 | 12.640 | 0,00% | – | 3,0 | 14% | 19% | ±2,3% |
| 100 | cache frio | 30 | 3.181 | 8.514 | 9.428 | 0,00% | 13% | 2,6 | 15% | 16% | ±2,8% |
| 100 | cache quente | 6.532 | 15,3 | 33,6 | 48,4 | 0,00% | 100% | 0,0 | 319% | 0% | ±14,0% |
| 200 | sem cache | 21 | 8.477 | 18.110 | 22.388 | 0,00% | – | 3,0 | 14% | 15% | ±2,1% |
| 200 | cache frio | 28 | 6.720 | 11.895 | 15.887 | 0,00% | 14% | 2,6 | 15% | 14% | ±4,1% |
| 200 | cache quente | 6.579 | 30,3 | 51,8 | 77,7 | 0,00% | 100% | 0,0 | 323% | 0% | ±8,1% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem cache | 3,3 | 6 | 39 | 8,603 | `SELECT count(*) AS count_1, max(emprestimo.data_emprestimo) AS max_1 FROM emprestimo WHERE…` |
| cache frio | 2,8 | 5 | 33 | 8,624 | `SELECT count(*) AS count_1, max(emprestimo.data_emprestimo) AS max_1 FROM emprestimo WHERE…` |
| cache quente | 0,0 | 0 | 0 | 0,025 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: cache frio com 10 VUs, cache frio com 50 VUs, sem cache com 50 VUs, cache frio com 100 VUs, sem cache com 100 VUs, cache frio com 200 VUs, sem cache com 200 VUs.

![Cenário 1: ficha do livro sem e com cache](graficos/cache.svg)

## Cenário 2: página de 20 empréstimos com livro e leitor

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | LAZY | 0,8 | 11.356 | 22.834 | 25.301 | 0,00% | 41,0 | 9% | 5% | ±10,0% |
| 10 | EAGER | 38 | 268 | 423 | 546 | 0,00% | 1,0 | 22% | 22% | ±23,4% |
| 10 | otimizada | 51 | 198 | 289 | 370 | 0,00% | 1,0 | 15% | 22% | ±7,7% |
| 10 | SQL nativo | 45 | 230 | 385 | 503 | 0,00% | 1,0 | 12% | 75% | ±25,3% |
| 50 | LAZY | 0,8 | 21.045 | 29.285 | 29.848 | 0,00% | 41,0 | 11% | 5% | ±60,9% |
| 50 | EAGER | 72 | 703 | 1.100 | 1.418 | 0,00% | 1,0 | 40% | 21% | ±0,1% |
| 50 | otimizada | 74 | 684 | 843 | 1.230 | 0,00% | 1,0 | 20% | 15% | ±7,7% |
| 50 | SQL nativo | 73 | 693 | 882 | 1.177 | 0,00% | 1,0 | 17% | 61% | ±10,0% |
| 100 | LAZY | 0,1 | 17.209 | 22.605 | 23.032 | 0,00% | 41,0 | 12% | 5% | ±66,7% |
| 100 | EAGER | 69 | 1.476 | 3.159 | 5.743 | 0,00% | 1,0 | 37% | 47% | ±5,1% |
| 100 | otimizada | 75 | 1.354 | 3.316 | 5.097 | 0,00% | 1,0 | 20% | 14% | ±5,4% |
| 100 | SQL nativo | 67 | 1.531 | 4.296 | 7.083 | 0,00% | 1,0 | 16% | 150% | ±13,1% |
| 200 | LAZY | 0,0 | 25.976 | 28.562 | 28.707 | 0,00% | 41,0 | 12% | 4% | – |
| 200 | EAGER | 62 | 3.241 | 7.273 | 9.659 | 0,00% | 1,0 | 37% | 114% | ±14,9% |
| 200 | otimizada | 75 | 2.688 | 6.188 | 8.508 | 0,00% | 1,0 | 21% | 13% | ±2,7% |
| 200 | SQL nativo | 66 | 3.183 | 7.474 | 10.569 | 0,00% | 1,0 | 17% | 151% | ±25,1% |

**LAZY com 200 VUs**: em 2 das 3 repetições nenhuma requisição terminou dentro da janela de medição (30 s); as latências são a média das outras.

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| LAZY | 239,9 | 353 | 1.231 | 272,498 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |
| EAGER | 1,0 | 20 | 152 | 10,408 | `SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestim…` |
| otimizada | 1,0 | 20 | 128 | 3,169 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| SQL nativo | 1,0 | 20 | 128 | 17,943 | `SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id AS livro_id, l.tit…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: LAZY com 10 VUs, EAGER com 50 VUs, LAZY com 50 VUs, SQL nativo com 50 VUs, EAGER com 100 VUs, LAZY com 100 VUs, SQL nativo com 100 VUs, otimizada com 100 VUs, EAGER com 200 VUs, LAZY com 200 VUs, SQL nativo com 200 VUs, otimizada com 200 VUs.

![Cenário 2: página de 20 empréstimos com livro e leitor](graficos/persistencia.svg)

## Cenário 3: histórico de empréstimos de um leitor, sem e com índice

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem índice | 32 | 319 | 447 | 615 | 0,00% | 1,0 | 11% | 351% | ±11,3% |
| 10 | com índice | 48 | 212 | 351 | 567 | 0,00% | 1,0 | 15% | 87% | ±18,4% |
| 50 | sem índice | 36 | 1.414 | 2.326 | 3.776 | 0,00% | 1,0 | 12% | 620% | ±1,9% |
| 50 | com índice | 71 | 720 | 1.343 | 1.683 | 0,00% | 1,0 | 20% | 47% | ±10,9% |
| 100 | sem índice | 37 | 2.741 | 5.320 | 9.473 | 0,00% | 1,0 | 13% | 603% | ±3,9% |
| 100 | com índice | 75 | 1.360 | 3.565 | 5.366 | 0,00% | 1,0 | 20% | 56% | ±2,4% |
| 200 | sem índice | 34 | 5.575 | 12.155 | 16.465 | 0,00% | 1,0 | 12% | 596% | ±2,5% |
| 200 | com índice | 72 | 2.813 | 6.377 | 8.659 | 0,00% | 1,0 | 19% | 76% | ±3,3% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem índice | 1,1 | 32 | 12.810 | 159,149 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| com índice | 1,0 | 30 | 132 | 10,084 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: com índice com 50 VUs, sem índice com 50 VUs, com índice com 100 VUs, sem índice com 100 VUs, com índice com 200 VUs, sem índice com 200 VUs.

![Cenário 3: histórico de empréstimos de um leitor, sem e com índice](graficos/indice.svg)

## Efeito do TTL (cache começando vazio)

| TTL | req/s | média (ms) | p95 (ms) | acertos no cache | acertos nos últimos 20 s | variação |
|---:|---:|---:|---:|---:|---:|---:|
| 5 s | 27 | 1.855 | 2.420 | 6% | 5% | ±1,2% |
| 30 s | 31 | 1.662 | 2.393 | 15% | 16% | ±3,9% |
| 120 s | 32 | 1.569 | 2.753 | 19% | 26% | ±2,7% |
| 600 s | 32 | 1.587 | 2.382 | 19% | 26% | ±5,3% |

![Taxa de acerto ao longo do tempo](graficos/ttl.svg)

## Memória

Maior leitura de memória do contêiner na janela de medição (memory.current do cgroup), em MB, média das repetições. A memória do servidor do banco não é acessível no Supabase.

| cenário | versão | API com 10 VUs | API com 50 VUs | API com 100 VUs | API com 200 VUs | Redis (todos os níveis) |
|---|---|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 380 | 388 | 396 | 401 | 7 a 8 |
| Cenário 1 | cache frio | 382 | 387 | 402 | 411 | 7 a 9 |
| Cenário 1 | cache quente | 548 | 520 | 521 | 530 | 31 a 32 |
| Cenário 2 | LAZY | 378 | 395 | 404 | 422 | 15 a 16 |
| Cenário 2 | EAGER | 387 | 415 | 436 | 444 | 9 a 17 |
| Cenário 2 | otimizada | 376 | 383 | 391 | 399 | 8 a 10 |
| Cenário 2 | SQL nativo | 373 | 382 | 388 | 395 | 8 a 10 |
| Cenário 3 | sem índice | 373 | 383 | 395 | 397 | 7 a 8 |
| Cenário 3 | com índice | 378 | 386 | 397 | 403 | 7 a 9 |

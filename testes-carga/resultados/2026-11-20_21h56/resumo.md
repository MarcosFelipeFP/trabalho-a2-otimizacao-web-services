# Resultados dos testes de desempenho

Gerado por `testes-carga/analisar.py` a partir das execuções do k6 desta pasta.

## Ambiente

- Data: 2026-11-20 21:56:17
- Máquina: AMD Ryzen 5 5600X 6-Core Processor, 12 núcleos lógicos, 15,9 GB; Windows-11-10.0.26200-SP0
- Docker: 29.7.2 | VM com 6 CPUs e 6214623232 bytes de memória
- k6: k6 v2.3.0 (commit/e088784614, go1.27.1, linux/amd64) (contêiner na rede da API)
- API: Python 3.14.10, 4 processos, 3 conexões por processo; fastapi 0.163.1, uvicorn 0.54.0, sqlalchemy 2.1.8, psycopg 3.3.9, redis 8.1.0, orjson 3.13.0
- Banco: PostgreSQL 17.12 em aws-1-us-east-2.pooler.supabase.com (74 MB nas tabelas da biblioteca; random_page_cost 1.1); cache: Redis 8.10.3
- Ida e volta da API até o banco (SELECT 1, 50 vezes): mediana 160,1 ms, mínimo 154,9 ms, máximo 319,3 ms
- Dados: categoria 20, autor 5.000, livro 20.000, leitor 10.000, emprestimo 300.000
- Cargas: 10,50,100,200 VUs; 10 s de aquecimento e 30 s de medição por nível; 3 repetições
- Outros contêineres em execução: petmotion-pc-worker-1 (petmotion:local), petmotion-pc-api-1 (petmotion:local)

## Comparação das versões com 50 VUs

| cenário | versão | latência média (ms) | p95 (ms) | p99 (ms) | vazão (req/s) | erros | SQL por req. |
|---|---|---:|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 2.009 | 2.888 | 5.433 | 25,4 | 0,00% | 3,0 |
| Cenário 1 | cache frio | 1.662 | 3.611 | 3.638 | 30,6 | 0,00% | 2,6 |
| Cenário 1 | cache quente | 8,60 | 18,5 | 28,9 | 5.713,0 | 0,00% | 0,0 |
| Cenário 2 | LAZY | 22.453 | 29.729 | 30.050 | 0,8 | 0,00% | 41,0 |
| Cenário 2 | EAGER | 674 | 808 | 1.217 | 75,0 | 0,00% | 1,0 |
| Cenário 2 | otimizada | 659 | 922 | 1.140 | 76,8 | 0,00% | 1,0 |
| Cenário 2 | SQL nativo | 725 | 1.115 | 1.309 | 71,1 | 0,00% | 1,0 |
| Cenário 3 | sem índice | 1.059 | 2.220 | 2.479 | 48,5 | 0,00% | 1,0 |
| Cenário 3 | com índice | 659 | 765 | 1.118 | 76,7 | 0,00% | 1,0 |

## Cenário 1: ficha do livro sem e com cache

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | acertos no cache | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem cache | 18 | 577 | 771 | 1.348 | 0,00% | – | 3,0 | 11% | 4% | ±18,2% |
| 10 | cache frio | 18 | 578 | 936 | 1.116 | 0,00% | 9% | 2,7 | 12% | 6% | ±11,3% |
| 10 | cache quente | 4.626 | 2,12 | 4,51 | 6,79 | 0,00% | 100% | 0,0 | 260% | 0% | ±27,7% |
| 50 | sem cache | 25 | 2.009 | 2.888 | 5.433 | 0,00% | – | 3,0 | 14% | 2% | ±1,5% |
| 50 | cache frio | 31 | 1.662 | 3.611 | 3.638 | 0,00% | 13% | 2,6 | 15% | 3% | ±1,7% |
| 50 | cache quente | 5.713 | 8,60 | 18,5 | 28,9 | 0,00% | 100% | 0,0 | 304% | 0% | ±6,1% |
| 100 | sem cache | 24 | 3.904 | 10.638 | 16.782 | 0,00% | – | 3,0 | 15% | 1% | ±2,3% |
| 100 | cache frio | 30 | 3.268 | 6.570 | 6.659 | 0,00% | 14% | 2,6 | 16% | 8% | ±0,4% |
| 100 | cache quente | 5.700 | 17,4 | 36,2 | 53,5 | 0,00% | 100% | 0,0 | 318% | 0% | ±8,6% |
| 200 | sem cache | 18 | 8.764 | 19.313 | 25.153 | 0,00% | – | 3,0 | 14% | 15% | ±28,3% |
| 200 | cache frio | 27 | 6.866 | 13.558 | 17.881 | 0,00% | 14% | 2,6 | 16% | 2% | ±2,6% |
| 200 | cache quente | 5.746 | 34,6 | 66,2 | 102 | 0,00% | 100% | 0,0 | 319% | 0% | ±13,0% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem cache | 3,4 | 6 | 37 | 2,481 | `SELECT livro.id, livro.titulo, livro.ano_publicacao FROM livro WHERE livro.autor_id = $1::…` |
| cache frio | 2,8 | 5 | 31 | 2,353 | `SELECT count(*) FROM emprestimo WHERE data_devolucao IS NULL` |
| cache quente | 0,0 | 0 | 0 | 0,002 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: cache frio com 50 VUs, sem cache com 50 VUs, cache frio com 100 VUs, sem cache com 100 VUs, cache frio com 200 VUs, sem cache com 200 VUs.

![Cenário 1: ficha do livro sem e com cache](graficos/cache.svg)

## Cenário 2: página de 20 empréstimos com livro e leitor

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | LAZY | 0,8 | 10.714 | 19.156 | 21.092 | 0,00% | 40,9 | – | 1% | ±15,1% |
| 10 | EAGER | 45 | 230 | 320 | 381 | 0,00% | 1,0 | 19% | 8% | ±18,4% |
| 10 | otimizada | 58 | 172 | 225 | 281 | 0,00% | 1,0 | 16% | 3% | ±5,8% |
| 10 | SQL nativo | 48 | 218 | 305 | 381 | 0,00% | 1,0 | 12% | 4% | ±30,9% |
| 50 | LAZY | 0,8 | 22.453 | 29.729 | 30.050 | 0,00% | 41,0 | – | 3% | ±50,0% |
| 50 | EAGER | 75 | 674 | 808 | 1.217 | 0,00% | 1,0 | 30% | 7% | ±0,7% |
| 50 | otimizada | 77 | 659 | 922 | 1.140 | 0,00% | 1,0 | 21% | 3% | ±3,3% |
| 50 | SQL nativo | 71 | 725 | 1.115 | 1.309 | 0,00% | 1,0 | 16% | 4% | ±17,0% |
| 100 | LAZY | 0,2 | 18.353 | 27.627 | 28.617 | 0,00% | 41,0 | – | 3% | ±50,0% |
| 100 | EAGER | 74 | 1.379 | 2.802 | 4.624 | 0,00% | 1,0 | 28% | 7% | ±1,8% |
| 100 | otimizada | 77 | 1.335 | 3.476 | 5.059 | 0,00% | 1,0 | 22% | 6% | ±3,4% |
| 100 | SQL nativo | 77 | 1.320 | 3.299 | 4.928 | 0,00% | 1,0 | 18% | 4% | ±1,9% |
| 200 | LAZY | 0,0 | – | – | – | – | – | – | 2% | – |
| 200 | EAGER | 73 | 2.746 | 5.613 | 8.336 | 0,00% | 1,0 | 29% | 7% | ±1,5% |
| 200 | otimizada | 75 | 2.698 | 5.957 | 8.695 | 0,00% | 1,0 | 23% | 3% | ±3,2% |
| 200 | SQL nativo | 76 | 2.671 | 6.417 | 8.810 | 0,00% | 1,0 | 20% | 3% | ±2,3% |

**LAZY com 200 VUs**: em nenhuma das 3 repetições uma requisição terminou dentro da janela de medição (30 s); a vazão é zero e não há latência para mostrar.

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| LAZY | 199,2 | 293 | 881 | 93,782 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |
| EAGER | 1,0 | 20 | 127 | 1,735 | `SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestim…` |
| otimizada | 1,0 | 20 | 127 | 0,562 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| SQL nativo | 1,0 | 20 | 127 | 0,789 | `SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id AS livro_id, l.tit…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: LAZY com 10 VUs, LAZY com 50 VUs, SQL nativo com 50 VUs, otimizada com 50 VUs, EAGER com 100 VUs, LAZY com 100 VUs, SQL nativo com 100 VUs, otimizada com 100 VUs, EAGER com 200 VUs, LAZY com 200 VUs, SQL nativo com 200 VUs, otimizada com 200 VUs.

![Cenário 2: página de 20 empréstimos com livro e leitor](graficos/persistencia.svg)

## Cenário 3: histórico de empréstimos de um leitor, sem e com índice

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem índice | 35 | 321 | 439 | 669 | 0,00% | 1,0 | 12% | 211% | ±37,2% |
| 10 | com índice | 54 | 188 | 254 | 302 | 0,00% | 1,0 | 16% | 5% | ±10,4% |
| 50 | sem índice | 48 | 1.059 | 2.220 | 2.479 | 0,00% | 1,0 | 16% | 374% | ±7,8% |
| 50 | com índice | 77 | 659 | 765 | 1.118 | 0,00% | 1,0 | 20% | 2% | ±2,0% |
| 100 | sem índice | 52 | 1.964 | 4.857 | 7.256 | 0,00% | 1,0 | 17% | 383% | ±1,3% |
| 100 | com índice | 66 | 1.543 | 4.922 | 7.051 | 0,00% | 1,0 | 19% | 54% | ±14,7% |
| 200 | sem índice | 49 | 4.030 | 9.367 | 13.085 | 0,00% | 1,0 | 16% | 396% | ±2,0% |
| 200 | com índice | 75 | 2.683 | 6.228 | 9.002 | 0,00% | 1,0 | 22% | 3% | ±1,5% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem índice | 1,0 | 31 | 4.487 | 76,551 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| com índice | 1,0 | 31 | 132 | 2,335 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: sem índice com 50 VUs, com índice com 100 VUs, sem índice com 100 VUs, com índice com 200 VUs, sem índice com 200 VUs.

![Cenário 3: histórico de empréstimos de um leitor, sem e com índice](graficos/indice.svg)

## Efeito do TTL (cache começando vazio)

| TTL | req/s | média (ms) | p95 (ms) | acertos no cache | acertos nos últimos 20 s | variação |
|---:|---:|---:|---:|---:|---:|---:|
| 5 s | 27 | 1.804 | 2.238 | 6% | 5% | ±10,7% |
| 30 s | 31 | 1.622 | 2.308 | 14% | 17% | ±0,1% |
| 120 s | 32 | 1.565 | 2.530 | 19% | 27% | ±5,8% |
| 600 s | 33 | 1.553 | 2.285 | 18% | 24% | ±3,5% |

![Taxa de acerto ao longo do tempo](graficos/ttl.svg)

## Memória

Maior leitura de memória do contêiner na janela de medição (memory.current do cgroup), em MB, média das repetições. A memória do servidor do banco não é acessível no Supabase.

| cenário | versão | API com 10 VUs | API com 50 VUs | API com 100 VUs | API com 200 VUs | Redis (todos os níveis) |
|---|---|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 380 | 378 | 390 | 398 | 27 a 28 |
| Cenário 1 | cache frio | 372 | 383 | 394 | 401 | 28 a 30 |
| Cenário 1 | cache quente | 574 | 552 | 554 | 540 | 52 a 53 |
| Cenário 2 | LAZY | – | – | – | – | 28 a 30 |
| Cenário 2 | EAGER | 372 | 390 | 401 | 411 | 27 a 30 |
| Cenário 2 | otimizada | 368 | 374 | 382 | 392 | 27 a 28 |
| Cenário 2 | SQL nativo | 368 | 369 | 382 | 380 | 27 |
| Cenário 3 | sem índice | 365 | 377 | 383 | 391 | 27 |
| Cenário 3 | com índice | 366 | 377 | 381 | 394 | 27 a 29 |

Traço: memória não registrada nessa execução.

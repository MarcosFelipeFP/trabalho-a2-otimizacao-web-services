# Resultados dos testes de desempenho

Gerado por `testes-carga/analisar.py` a partir das execuções do k6 desta pasta.

## Ambiente

- Data: 2026-11-24 01:52:56
- Máquina: AMD Ryzen 5 5600X 6-Core Processor, 12 núcleos lógicos, 23,9 GB; Windows-11-10.0.26200-SP0
- Docker: 29.7.2 | VM com 6 CPUs e 6214619136 bytes de memória
- k6: k6 v2.3.0 (commit/e088784614, go1.27.1, linux/amd64) (contêiner na rede da API)
- API: Python 3.14.10, 4 processos, 3 conexões por processo; fastapi 0.163.1, uvicorn 0.54.0, sqlalchemy 2.1.8, psycopg 3.3.9, redis 8.1.0, orjson 3.13.0
- Banco: PostgreSQL 17.12 em aws-1-us-east-2.pooler.supabase.com (165 MB nas tabelas da biblioteca; random_page_cost 1.1); cache: Redis 8.10.3
- Ida e volta da API até o banco (SELECT 1, 50 vezes): mediana 158,6 ms, mínimo 148,5 ms, máximo 301,4 ms
- Dados: categoria 20, autor 5.000, livro 20.000, leitor 10.000, emprestimo 300.000
- Cargas: 10,50,100,200 VUs; 10 s de aquecimento e 30 s de medição por nível; 1 repetições
- Outros contêineres em execução: petmotion-pc-worker-1 (petmotion:local), petmotion-pc-api-1 (petmotion:local)

## Comparação das versões com 50 VUs

| cenário | versão | latência média (ms) | p95 (ms) | p99 (ms) | vazão (req/s) | erros | SQL por req. |
|---|---|---:|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 2.067 | 4.361 | 4.876 | 24,3 | 0,00% | 3,0 |
| Cenário 1 | cache frio | 1.738 | 2.845 | 3.446 | 29,5 | 0,00% | 2,6 |
| Cenário 1 | cache quente | 7,92 | 18,9 | 26,3 | 6.195,4 | 0,00% | 0,0 |
| Cenário 2 | LAZY | 21.038 | 30.717 | 31.158 | 0,7 | 0,00% | 41,0 |
| Cenário 2 | EAGER | 711 | 946 | 1.424 | 71,1 | 0,00% | 1,0 |
| Cenário 2 | otimizada | 742 | 1.612 | 1.627 | 68,7 | 0,00% | 1,0 |
| Cenário 2 | SQL nativo | 658 | 818 | 1.055 | 76,8 | 0,00% | 1,0 |
| Cenário 3 | sem índice | 1.421 | 2.041 | 2.737 | 36,1 | 0,00% | 1,0 |
| Cenário 3 | com índice | 687 | 896 | 1.157 | 73,6 | 0,00% | 1,0 |

## Cenário 1: ficha do livro sem e com cache

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | acertos no cache | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem cache | 16 | 614 | 943 | 1.141 | 0,00% | – | 3,0 | 11% | 7% | – |
| 10 | cache frio | 23 | 433 | 491 | 947 | 0,00% | 12% | 2,7 | 13% | 12% | – |
| 10 | cache quente | 5.016 | 1,86 | 4,11 | 6,79 | 0,00% | 100% | 0,0 | 295% | 0% | – |
| 50 | sem cache | 24 | 2.067 | 4.361 | 4.876 | 0,00% | – | 3,0 | 15% | 20% | – |
| 50 | cache frio | 29 | 1.738 | 2.845 | 3.446 | 0,00% | 12% | 2,6 | 13% | 13% | – |
| 50 | cache quente | 6.195 | 7,92 | 18,9 | 26,3 | 0,00% | 100% | 0,0 | 311% | 0% | – |
| 100 | sem cache | 16 | 6.036 | 14.955 | 16.870 | 0,00% | – | 3,0 | 10% | 12% | – |
| 100 | cache frio | 28 | 3.503 | 5.681 | 12.861 | 0,00% | 13% | 2,6 | 14% | 13% | – |
| 100 | cache quente | 6.558 | 15,1 | 28,0 | 38,1 | 0,00% | 100% | 0,0 | 321% | 0% | – |
| 200 | sem cache | 20 | 8.612 | 16.937 | 25.217 | 0,00% | – | 3,0 | 13% | 11% | – |
| 200 | cache frio | 26 | 7.232 | 13.322 | 18.120 | 0,00% | 13% | 2,6 | 14% | 24% | – |
| 200 | cache quente | 6.192 | 32,1 | 54,3 | 80,9 | 0,00% | 100% | 0,0 | 322% | 0% | – |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem cache | 3,4 | 6 | 40 | 6,760 | `SELECT count(*) AS count_1, max(emprestimo.data_emprestimo) AS max_1 FROM emprestimo WHERE…` |
| cache frio | 2,8 | 5 | 33 | 6,614 | `SELECT count(*) AS count_1, max(emprestimo.data_emprestimo) AS max_1 FROM emprestimo WHERE…` |
| cache quente | 0,0 | 0 | 0 | 0,015 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: cache frio com 50 VUs, sem cache com 50 VUs, cache frio com 100 VUs, sem cache com 100 VUs, cache frio com 200 VUs, sem cache com 200 VUs.

![Cenário 1: ficha do livro sem e com cache](graficos/cache.svg)

## Cenário 2: página de 20 empréstimos com livro e leitor

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | LAZY | 1,0 | 8.940 | 22.974 | 26.121 | 0,00% | 41,0 | 9% | 6% | – |
| 10 | EAGER | 36 | 276 | 477 | 512 | 0,00% | 1,0 | 21% | 21% | – |
| 10 | otimizada | 54 | 184 | 306 | 322 | 0,00% | 1,0 | 13% | 17% | – |
| 10 | SQL nativo | 62 | 162 | 169 | 278 | 0,00% | 1,0 | 14% | 22% | – |
| 50 | LAZY | 0,7 | 21.038 | 30.717 | 31.158 | 0,00% | 41,0 | 11% | 5% | – |
| 50 | EAGER | 71 | 711 | 946 | 1.424 | 0,00% | 1,0 | 38% | 23% | – |
| 50 | otimizada | 69 | 742 | 1.612 | 1.627 | 0,00% | 1,0 | 17% | 13% | – |
| 50 | SQL nativo | 77 | 658 | 818 | 1.055 | 0,00% | 1,0 | 16% | 18% | – |
| 100 | LAZY | 0,3 | 20.976 | 29.432 | 30.601 | 0,00% | 41,0 | 11% | 4% | – |
| 100 | EAGER | 72 | 1.433 | 2.281 | 4.229 | 0,00% | 1,0 | 38% | 18% | – |
| 100 | otimizada | 74 | 1.363 | 4.812 | 6.942 | 0,00% | 1,0 | 18% | 15% | – |
| 100 | SQL nativo | 68 | 1.491 | 3.298 | 6.981 | 0,00% | 1,0 | 15% | 139% | – |
| 200 | LAZY | 0,0 | – | – | – | – | – | 11% | 3% | – |
| 200 | EAGER | 69 | 2.895 | 6.655 | 9.705 | 0,00% | 1,0 | 39% | 20% | – |
| 200 | otimizada | 73 | 2.768 | 6.569 | 8.704 | 0,00% | 1,0 | 19% | 13% | – |
| 200 | SQL nativo | 58 | 3.461 | 7.701 | 10.311 | 0,00% | 1,0 | 15% | 272% | – |

**LAZY com 200 VUs**: em nenhuma das 1 repetições uma requisição terminou dentro da janela de medição (30 s); a vazão é zero e não há latência para mostrar.

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| LAZY | 193,3 | 284 | 1.019 | 206,353 | `SELECT count(*) FROM emprestimo WHERE data_devolucao IS NULL` |
| EAGER | 1,0 | 20 | 152 | 3,849 | `SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestim…` |
| otimizada | 1,0 | 20 | 128 | 2,773 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| SQL nativo | 1,0 | 20 | 129 | 19,399 | `SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id AS livro_id, l.tit…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: LAZY com 10 VUs, LAZY com 50 VUs, otimizada com 50 VUs, EAGER com 100 VUs, LAZY com 100 VUs, SQL nativo com 100 VUs, otimizada com 100 VUs, EAGER com 200 VUs, LAZY com 200 VUs, SQL nativo com 200 VUs, otimizada com 200 VUs.

![Cenário 2: página de 20 empréstimos com livro e leitor](graficos/persistencia.svg)

## Cenário 3: histórico de empréstimos de um leitor, sem e com índice

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem índice | 30 | 331 | 477 | 696 | 0,00% | 1,0 | 10% | 394% | – |
| 10 | com índice | 42 | 239 | 347 | 463 | 0,00% | 1,0 | 13% | 39% | – |
| 50 | sem índice | 36 | 1.421 | 2.041 | 2.737 | 0,00% | 1,0 | 11% | 606% | – |
| 50 | com índice | 74 | 687 | 896 | 1.157 | 0,00% | 1,0 | 17% | 83% | – |
| 100 | sem índice | 36 | 2.764 | 6.799 | 11.857 | 0,00% | 1,0 | 12% | 600% | – |
| 100 | com índice | 73 | 1.388 | 2.257 | 4.361 | 0,00% | 1,0 | 19% | 46% | – |
| 200 | sem índice | 33 | 5.751 | 13.177 | 16.972 | 0,00% | 1,0 | 12% | 607% | – |
| 200 | com índice | 75 | 2.666 | 6.292 | 8.268 | 0,00% | 1,0 | 19% | 23% | – |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem índice | 1,1 | 32 | 12.815 | 164,127 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| com índice | 1,0 | 30 | 126 | 9,934 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: sem índice com 50 VUs, com índice com 100 VUs, sem índice com 100 VUs, com índice com 200 VUs, sem índice com 200 VUs.

![Cenário 3: histórico de empréstimos de um leitor, sem e com índice](graficos/indice.svg)

## Memória

Maior leitura de memória do contêiner na janela de medição (memory.current do cgroup), em MB, média das repetições. A memória do servidor do banco não é acessível no Supabase.

| cenário | versão | API com 10 VUs | API com 50 VUs | API com 100 VUs | API com 200 VUs | Redis (todos os níveis) |
|---|---|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 382 | 392 | 391 | 405 | 9 a 14 |
| Cenário 1 | cache frio | 376 | 396 | 402 | 413 | 10 a 12 |
| Cenário 1 | cache quente | 573 | 510 | 514 | 520 | 33 a 34 |
| Cenário 2 | LAZY | 383 | 395 | 407 | 420 | 33 a 38 |
| Cenário 2 | EAGER | 388 | 414 | 431 | 444 | 15 a 34 |
| Cenário 2 | otimizada | 378 | 385 | 391 | 396 | 12 |
| Cenário 2 | SQL nativo | 372 | 377 | 392 | 394 | 12 |
| Cenário 3 | sem índice | 374 | 385 | 390 | 402 | 11 a 12 |
| Cenário 3 | com índice | 376 | 378 | 393 | 401 | 10 a 14 |

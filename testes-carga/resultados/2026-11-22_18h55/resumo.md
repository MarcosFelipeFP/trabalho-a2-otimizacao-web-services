# Resultados dos testes de desempenho

Gerado por `testes-carga/analisar.py` a partir das execuções do k6 desta pasta.

## Ambiente

- Data: 2026-11-22 18:55:37
- Máquina: AMD Ryzen 5 5600X 6-Core Processor, 12 núcleos lógicos, 23,9 GB; Windows-11-10.0.26200-SP0
- Docker: 29.7.2 | VM com 6 CPUs e 6214619136 bytes de memória
- k6: k6 v2.3.0 (commit/e088784614, go1.27.1, linux/amd64) (contêiner na rede da API)
- API: Python 3.14.10, 4 processos, 3 conexões por processo; fastapi 0.163.1, uvicorn 0.54.0, sqlalchemy 2.1.8, psycopg 3.3.9, redis 8.1.0, orjson 3.13.0
- Banco: PostgreSQL 17.11 em banco (165 MB nas tabelas da biblioteca; random_page_cost 4); cache: Redis 8.10.3
- Ida e volta da API até o banco (SELECT 1, 50 vezes): mediana 0,2 ms, mínimo 0,2 ms, máximo 0,6 ms
- Dados: categoria 20, autor 5.000, livro 20.000, leitor 10.000, emprestimo 300.000
- Cargas: 10,50,100,200 VUs; 10 s de aquecimento e 30 s de medição por nível; 3 repetições
- Outros contêineres em execução: petmotion-pc-worker-1 (petmotion:local), petmotion-pc-api-1 (petmotion:local)

## Comparação das versões com 50 VUs

| cenário | versão | latência média (ms) | p95 (ms) | p99 (ms) | vazão (req/s) | erros | SQL por req. |
|---|---|---:|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 34,4 | 72,7 | 107 | 1.451,5 | 0,00% | 3,0 |
| Cenário 1 | cache frio | 13,8 | 41,1 | 95,6 | 3.612,7 | 0,00% | 0,5 |
| Cenário 1 | cache quente | 7,66 | 16,4 | 25,9 | 6.449,8 | 0,00% | 0,0 |
| Cenário 2 | LAZY | 291 | 465 | 665 | 173,8 | 0,00% | 41,0 |
| Cenário 2 | EAGER | 45,5 | 138 | 227 | 1.100,7 | 0,00% | 1,0 |
| Cenário 2 | otimizada | 24,3 | 60,3 | 94,4 | 2.057,1 | 0,00% | 1,0 |
| Cenário 2 | SQL nativo | 20,5 | 48,9 | 77,4 | 2.469,5 | 0,00% | 1,0 |
| Cenário 3 | sem índice | 416 | 1.040 | 1.453 | 122,6 | 0,00% | 1,0 |
| Cenário 3 | com índice | 20,1 | 54,4 | 87,9 | 2.488,0 | 0,00% | 1,0 |

## Cenário 1: ficha do livro sem e com cache

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | acertos no cache | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem cache | 1.370 | 7,39 | 17,7 | 24,3 | 0,00% | – | 3,0 | 318% | 13% | ±22,7% |
| 10 | cache frio | 3.312 | 2,96 | 8,93 | 13,8 | 0,00% | 81% | 0,6 | 311% | 6% | ±18,0% |
| 10 | cache quente | 5.588 | 1,69 | 3,29 | 5,10 | 0,00% | 100% | 0,0 | 291% | 0% | ±11,1% |
| 50 | sem cache | 1.452 | 34,4 | 72,7 | 107 | 0,00% | – | 3,0 | 359% | 14% | ±6,9% |
| 50 | cache frio | 3.613 | 13,8 | 41,1 | 95,6 | 0,00% | 83% | 0,5 | 337% | 7% | ±12,6% |
| 50 | cache quente | 6.450 | 7,66 | 16,4 | 25,9 | 0,00% | 100% | 0,0 | 316% | 0% | ±13,9% |
| 100 | sem cache | 1.301 | 76,8 | 175 | 265 | 0,00% | – | 3,0 | 350% | 14% | ±3,3% |
| 100 | cache frio | 3.320 | 30,6 | 107 | 251 | 0,00% | 81% | 0,6 | 334% | 7% | ±19,3% |
| 100 | cache quente | 6.294 | 16,3 | 35,7 | 62,1 | 0,00% | 100% | 0,0 | 311% | 0% | ±25,6% |
| 200 | sem cache | 1.297 | 155 | 353 | 513 | 0,00% | – | 3,0 | 351% | 15% | ±7,0% |
| 200 | cache frio | 3.072 | 69,0 | 241 | 420 | 0,00% | 79% | 0,6 | 337% | 7% | ±30,8% |
| 200 | cache quente | 6.089 | 34,5 | 63,8 | 94,9 | 0,00% | 100% | 0,0 | 322% | 0% | ±30,5% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem cache | 3,0 | 6 | 32 | 0,100 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |
| cache frio | 0,5 | 1 | 5 | 0,017 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |
| cache quente | 0,0 | 0 | 0 | 0,001 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |

Todos os níveis respeitaram os limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%).

![Cenário 1: ficha do livro sem e com cache](graficos/cache.svg)

## Cenário 2: página de 20 empréstimos com livro e leitor

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | LAZY | 166 | 61,1 | 104 | 131 | 0,00% | 41,0 | 370% | 14% | ±16,9% |
| 10 | EAGER | 990 | 10,4 | 21,1 | 29,6 | 0,00% | 1,0 | 282% | 76% | ±26,0% |
| 10 | otimizada | 2.098 | 4,64 | 9,29 | 13,0 | 0,00% | 1,0 | 282% | 46% | ±6,8% |
| 10 | SQL nativo | 2.494 | 3,92 | 7,52 | 11,4 | 0,00% | 1,0 | 266% | 59% | ±15,5% |
| 50 | LAZY | 174 | 291 | 465 | 665 | 0,00% | 41,0 | 380% | 22% | ±10,5% |
| 50 | EAGER | 1.101 | 45,5 | 138 | 227 | 0,00% | 1,0 | 309% | 89% | ±8,2% |
| 50 | otimizada | 2.057 | 24,3 | 60,3 | 94,4 | 0,00% | 1,0 | 299% | 53% | ±11,7% |
| 50 | SQL nativo | 2.470 | 20,5 | 48,9 | 77,4 | 0,00% | 1,0 | 278% | 66% | ±18,2% |
| 100 | LAZY | 174 | 587 | 983 | 1.613 | 0,00% | 41,0 | 382% | 14% | ±16,1% |
| 100 | EAGER | 1.008 | 99,6 | 274 | 454 | 0,00% | 1,0 | 306% | 85% | ±9,8% |
| 100 | otimizada | 1.944 | 51,6 | 123 | 182 | 0,00% | 1,0 | 299% | 51% | ±10,8% |
| 100 | SQL nativo | 2.225 | 47,9 | 115 | 175 | 0,00% | 1,0 | 280% | 64% | ±33,0% |
| 200 | LAZY | 164 | 1.275 | 2.587 | 3.403 | 0,00% | 41,0 | 382% | 14% | ±20,1% |
| 200 | EAGER | 1.010 | 201 | 513 | 751 | 0,00% | 1,0 | 305% | 83% | ±14,2% |
| 200 | otimizada | 1.968 | 102 | 248 | 362 | 0,00% | 1,0 | 298% | 50% | ±8,7% |
| 200 | SQL nativo | 2.164 | 94,1 | 227 | 334 | 0,00% | 1,0 | 277% | 62% | ±18,9% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| LAZY | 41,0 | 60 | 149 | 0,845 | `SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.pagi…` |
| EAGER | 1,0 | 20 | 148 | 0,826 | `SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestim…` |
| otimizada | 1,0 | 20 | 125 | 0,247 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| SQL nativo | 1,0 | 20 | 125 | 0,277 | `SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id AS livro_id, l.tit…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: LAZY com 100 VUs, LAZY com 200 VUs.

![Cenário 2: página de 20 empréstimos com livro e leitor](graficos/persistencia.svg)

## Cenário 3: histórico de empréstimos de um leitor, sem e com índice

| VUs | versão | req/s | média (ms) | p95 (ms) | p99 (ms) | erros | SQL por req. | CPU da API | banco executando | variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem índice | 119 | 85,1 | 146 | 191 | 0,00% | 1,0 | 33% | 719% | ±14,9% |
| 10 | com índice | 2.194 | 4,57 | 8,36 | 11,5 | 0,00% | 1,0 | 292% | 27% | ±20,8% |
| 50 | sem índice | 123 | 416 | 1.040 | 1.453 | 0,00% | 1,0 | 36% | 1.080% | ±16,1% |
| 50 | com índice | 2.488 | 20,1 | 54,4 | 87,9 | 0,00% | 1,0 | 335% | 32% | ±13,4% |
| 100 | sem índice | 135 | 750 | 1.517 | 2.444 | 0,00% | 1,0 | 37% | 1.142% | ±6,3% |
| 100 | com índice | 2.427 | 41,2 | 98,2 | 147 | 0,00% | 1,0 | 337% | 32% | ±8,2% |
| 200 | sem índice | 135 | 1.527 | 3.022 | 3.960 | 0,00% | 1,0 | 37% | 1.141% | ±9,8% |
| 200 | com índice | 2.363 | 85,4 | 205 | 304 | 0,00% | 1,0 | 336% | 31% | ±12,4% |

CPU da API em % de um núcleo (400% = quatro núcleos ocupados). Banco executando: soma do tempo de execução das consultas da API no banco (pg_stat_statements) dividida pela duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao mesmo tempo (com os dados em memória, executar é usar a CPU do banco ou esperar por ela). Variação: maior distância entre a vazão de uma repetição e a média.

Comportamento do banco (pg_stat_statements), por requisição, somando todas as execuções da versão (aquecimento e medição de todos os níveis):

| versão | consultas | linhas devolvidas | blocos lidos | tempo de execução no banco (ms) | comando mais custoso |
|---|---:|---:|---:|---:|---|
| sem índice | 1,0 | 30 | 12.108 | 79,533 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |
| com índice | 1,0 | 30 | 123 | 0,128 | `SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.dat…` |

Limites do k6 (p95 < 1 s, p99 < 2 s, erros < 1%) estourados em: sem índice com 50 VUs, sem índice com 100 VUs, sem índice com 200 VUs.

![Cenário 3: histórico de empréstimos de um leitor, sem e com índice](graficos/indice.svg)

## Memória

Maior leitura de memória do contêiner na janela de medição (memory.current do cgroup), em MB, média das repetições. A memória do servidor do banco não é acessível no Supabase.

| cenário | versão | API com 10 VUs | API com 50 VUs | API com 100 VUs | API com 200 VUs | Redis (todos os níveis) |
|---|---|---:|---:|---:|---:|---:|
| Cenário 1 | sem cache | 379 | 388 | 395 | 405 | 7 a 8 |
| Cenário 1 | cache frio | 384 | 399 | 408 | 421 | 28 a 30 |
| Cenário 1 | cache quente | 530 | 534 | 542 | 554 | 30 a 34 |
| Cenário 2 | LAZY | 382 | 399 | 416 | 422 | 16 a 23 |
| Cenário 2 | EAGER | 386 | 411 | 425 | 443 | 16 a 18 |
| Cenário 2 | otimizada | 379 | 386 | 393 | 400 | 15 a 23 |
| Cenário 2 | SQL nativo | 376 | 380 | 385 | 395 | 14 a 17 |
| Cenário 3 | sem índice | 379 | 385 | 397 | 403 | 7 a 8 |
| Cenário 3 | com índice | 373 | 388 | 397 | 407 | 6 a 7 |

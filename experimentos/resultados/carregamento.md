### Consultas SQL por requisição, conforme a quantidade de empréstimos da página

| estratégia | 10 | 50 | 100 | 200 | 500 |
|---|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 21 | 101 | 200 | 398 | 983 |
| EAGER (lazy="joined") | 1 | 1 | 1 | 1 | 1 |
| EAGER com SELECT ... IN | 3 | 3 | 3 | 3 | 3 |
| EAGER imediato, um SELECT por objeto | 21 | 101 | 200 | 398 | 983 |
| JOIN FETCH (joinedload) | 1 | 1 | 1 | 1 | 1 |
| otimizada (projeção com JOIN) | 1 | 1 | 1 | 1 | 1 |
| SQL nativo | 1 | 1 | 1 | 1 | 1 |

### Tempo no servidor (ms, mediana), conforme a quantidade de empréstimos da página

| estratégia | 10 | 50 | 100 | 200 | 500 |
|---|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 3.385,6 | 16.078,1 | 31.874,2 | 63.484,4 | 157.635,5 |
| EAGER (lazy="joined") | 162,1 | 167,7 | 172,3 | 190,1 | 205,7 |
| EAGER com SELECT ... IN | 484,8 | 487,1 | 501,4 | 518,0 | 550,2 |
| EAGER imediato, um SELECT por objeto | 3.350,2 | 16.066,2 | 31.860,0 | 63.252,3 | 157.603,9 |
| JOIN FETCH (joinedload) | 165,8 | 167,4 | 177,6 | 189,6 | 212,5 |
| otimizada (projeção com JOIN) | 160,7 | 161,4 | 163,3 | 164,2 | 166,9 |
| SQL nativo | 160,1 | 161,5 | 163,2 | 164,0 | 167,6 |

### Detalhe por quantidade

#### 10 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 21 | 30 | 13,5 | 2,3 | 3.373,58 | 3.385,64 |
| EAGER (lazy="joined") | 1 | 10 | 13,5 | 2,3 | 160,66 | 162,14 |
| EAGER com SELECT ... IN | 3 | 30 | 13,5 | 2,3 | 480,87 | 484,83 |
| EAGER imediato, um SELECT por objeto | 21 | 30 | 13,5 | 2,3 | 3.337,28 | 3.350,22 |
| JOIN FETCH (joinedload) | 1 | 10 | 13,5 | 2,3 | 163,23 | 165,83 |
| otimizada (projeção com JOIN) | 1 | 10 | 1,1 | 2,3 | 159,14 | 160,65 |
| SQL nativo | 1 | 10 | 1,1 | 2,3 | 159,23 | 160,14 |

#### 50 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 101 | 150 | 68,8 | 11,4 | 16.021,74 | 16.078,14 |
| EAGER (lazy="joined") | 1 | 50 | 68,8 | 11,4 | 164,84 | 167,72 |
| EAGER com SELECT ... IN | 3 | 150 | 68,8 | 11,4 | 481,84 | 487,06 |
| EAGER imediato, um SELECT por objeto | 101 | 150 | 68,8 | 11,4 | 16.008,95 | 16.066,17 |
| JOIN FETCH (joinedload) | 1 | 50 | 68,8 | 11,4 | 164,76 | 167,42 |
| otimizada (projeção com JOIN) | 1 | 50 | 5,4 | 11,4 | 159,88 | 161,42 |
| SQL nativo | 1 | 50 | 5,4 | 11,4 | 160,44 | 161,52 |

#### 100 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 200 | 299 | 136,6 | 22,8 | 31.766,34 | 31.874,22 |
| EAGER (lazy="joined") | 1 | 100 | 137,5 | 22,8 | 167,59 | 172,29 |
| EAGER com SELECT ... IN | 3 | 299 | 136,6 | 22,8 | 493,62 | 501,38 |
| EAGER imediato, um SELECT por objeto | 200 | 299 | 136,6 | 22,8 | 31.746,45 | 31.859,95 |
| JOIN FETCH (joinedload) | 1 | 100 | 137,5 | 22,8 | 173,36 | 177,62 |
| otimizada (projeção com JOIN) | 1 | 100 | 10,8 | 22,8 | 161,77 | 163,34 |
| SQL nativo | 1 | 100 | 10,8 | 22,8 | 161,93 | 163,22 |

#### 200 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 398 | 597 | 272,2 | 45,6 | 63.267,59 | 63.484,45 |
| EAGER (lazy="joined") | 1 | 200 | 273,8 | 45,6 | 183,58 | 190,14 |
| EAGER com SELECT ... IN | 3 | 597 | 272,2 | 45,6 | 506,92 | 518,00 |
| EAGER imediato, um SELECT por objeto | 398 | 597 | 272,2 | 45,6 | 63.030,08 | 63.252,29 |
| JOIN FETCH (joinedload) | 1 | 200 | 273,8 | 45,6 | 182,93 | 189,55 |
| otimizada (projeção com JOIN) | 1 | 200 | 21,6 | 45,6 | 162,40 | 164,20 |
| SQL nativo | 1 | 200 | 21,6 | 45,6 | 162,62 | 164,00 |

#### 500 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 983 | 1.482 | 674,9 | 114,2 | 157.095,24 | 157.635,45 |
| EAGER (lazy="joined") | 1 | 500 | 685,1 | 114,2 | 189,13 | 205,74 |
| EAGER com SELECT ... IN | 3 | 1.482 | 674,9 | 114,2 | 527,69 | 550,23 |
| EAGER imediato, um SELECT por objeto | 983 | 1.482 | 674,9 | 114,2 | 156.999,58 | 157.603,92 |
| JOIN FETCH (joinedload) | 1 | 500 | 685,1 | 114,2 | 188,90 | 212,46 |
| otimizada (projeção com JOIN) | 1 | 500 | 54,1 | 114,2 | 164,04 | 166,88 |
| SQL nativo | 1 | 500 | 54,1 | 114,2 | 165,24 | 167,60 |

### Resposta que não usa livro nem leitor (versões "resumo")

| empréstimos | mapeamento | consultas SQL | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---:|---|---:|---:|---:|---:|---:|
| 20 | LAZY | 1 | 2,0 | 3,0 | 158,98 | 160,67 |
| 20 | EAGER | 1 | 27,1 | 3,0 | 162,43 | 164,44 |
| 500 | LAZY | 1 | 51,7 | 75,8 | 164,49 | 169,20 |
| 500 | EAGER | 1 | 685,1 | 75,8 | 187,33 | 205,98 |

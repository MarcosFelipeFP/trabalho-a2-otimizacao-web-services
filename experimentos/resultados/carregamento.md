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
| LAZY (lazy="select") | 3.303,6 | 15.863,7 | 31.916,8 | 63.505,1 | 156.557,7 |
| EAGER (lazy="joined") | 164,0 | 170,9 | 178,0 | 197,6 | 244,6 |
| EAGER com SELECT ... IN | 477,7 | 491,1 | 510,2 | 543,5 | 619,1 |
| EAGER imediato, um SELECT por objeto | 3.302,3 | 15.889,1 | 31.372,9 | 63.248,4 | 155.688,2 |
| JOIN FETCH (joinedload) | 162,0 | 170,3 | 190,8 | 218,9 | 256,4 |
| otimizada (projeção com JOIN) | 158,8 | 159,2 | 159,5 | 163,6 | 168,5 |
| SQL nativo | 157,0 | 158,1 | 159,7 | 162,8 | 165,6 |

### Detalhe por quantidade

#### 10 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 21 | 30 | 30,8 | 2,3 | 3.291,08 | 3.303,64 |
| EAGER (lazy="joined") | 1 | 10 | 30,8 | 2,3 | 162,26 | 163,97 |
| EAGER com SELECT ... IN | 3 | 30 | 30,8 | 2,3 | 474,45 | 477,68 |
| EAGER imediato, um SELECT por objeto | 21 | 30 | 30,8 | 2,3 | 3.288,04 | 3.302,31 |
| JOIN FETCH (joinedload) | 1 | 10 | 30,8 | 2,3 | 160,09 | 162,01 |
| otimizada (projeção com JOIN) | 1 | 10 | 1,1 | 2,3 | 157,49 | 158,75 |
| SQL nativo | 1 | 10 | 1,1 | 2,3 | 156,10 | 156,97 |

#### 50 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 101 | 150 | 153,9 | 11,4 | 15.803,72 | 15.863,72 |
| EAGER (lazy="joined") | 1 | 50 | 153,9 | 11,4 | 167,31 | 170,95 |
| EAGER com SELECT ... IN | 3 | 150 | 153,9 | 11,4 | 484,11 | 491,11 |
| EAGER imediato, um SELECT por objeto | 101 | 150 | 153,9 | 11,4 | 15.825,26 | 15.889,10 |
| JOIN FETCH (joinedload) | 1 | 50 | 153,9 | 11,4 | 165,41 | 170,33 |
| otimizada (projeção com JOIN) | 1 | 50 | 5,4 | 11,4 | 157,78 | 159,17 |
| SQL nativo | 1 | 50 | 5,4 | 11,4 | 156,89 | 158,09 |

#### 100 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 200 | 299 | 305,6 | 22,8 | 31.798,90 | 31.916,76 |
| EAGER (lazy="joined") | 1 | 100 | 307,5 | 22,8 | 172,34 | 178,02 |
| EAGER com SELECT ... IN | 3 | 299 | 305,6 | 22,8 | 500,82 | 510,21 |
| EAGER imediato, um SELECT por objeto | 200 | 299 | 305,6 | 22,8 | 31.247,01 | 31.372,94 |
| JOIN FETCH (joinedload) | 1 | 100 | 307,5 | 22,8 | 185,09 | 190,75 |
| otimizada (projeção com JOIN) | 1 | 100 | 10,8 | 22,8 | 157,96 | 159,48 |
| SQL nativo | 1 | 100 | 10,8 | 22,8 | 158,30 | 159,71 |

#### 200 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 398 | 597 | 610,8 | 45,6 | 63.267,77 | 63.505,07 |
| EAGER (lazy="joined") | 1 | 200 | 614,3 | 45,6 | 186,47 | 197,55 |
| EAGER com SELECT ... IN | 3 | 597 | 610,8 | 45,6 | 529,67 | 543,55 |
| EAGER imediato, um SELECT por objeto | 398 | 597 | 610,8 | 45,6 | 63.006,09 | 63.248,42 |
| JOIN FETCH (joinedload) | 1 | 200 | 614,3 | 45,6 | 208,85 | 218,87 |
| otimizada (projeção com JOIN) | 1 | 200 | 21,6 | 45,6 | 161,80 | 163,57 |
| SQL nativo | 1 | 200 | 21,6 | 45,6 | 160,73 | 162,76 |

#### 500 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 983 | 1.482 | 1.515,7 | 114,2 | 155.965,59 | 156.557,70 |
| EAGER (lazy="joined") | 1 | 500 | 1.538,3 | 114,2 | 220,92 | 244,62 |
| EAGER com SELECT ... IN | 3 | 1.482 | 1.515,7 | 114,2 | 588,55 | 619,09 |
| EAGER imediato, um SELECT por objeto | 983 | 1.482 | 1.515,7 | 114,2 | 155.082,96 | 155.688,19 |
| JOIN FETCH (joinedload) | 1 | 500 | 1.538,3 | 114,2 | 234,49 | 256,38 |
| otimizada (projeção com JOIN) | 1 | 500 | 54,1 | 114,2 | 165,74 | 168,53 |
| SQL nativo | 1 | 500 | 54,1 | 114,2 | 163,11 | 165,56 |

### Resposta que não usa livro nem leitor (versões "resumo")

| empréstimos | mapeamento | consultas SQL | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---:|---|---:|---:|---:|---:|---:|
| 20 | LAZY | 1 | 6,1 | 3,0 | 159,11 | 160,43 |
| 20 | EAGER | 1 | 61,5 | 3,0 | 164,28 | 166,36 |
| 500 | LAZY | 1 | 151,4 | 75,8 | 175,03 | 181,24 |
| 500 | EAGER | 1 | 1.538,3 | 75,8 | 235,09 | 259,78 |

### Consultas SQL por requisição, conforme a quantidade de empréstimos da página

| estratégia | 10 | 50 | 100 | 500 | 1.000 |
|---|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 21 | 101 | 200 | 983 | 1.922 |
| EAGER (lazy="joined") | 1 | 1 | 1 | 1 | 1 |
| EAGER com SELECT ... IN | 3 | 3 | 3 | 3 | 5 |
| EAGER imediato, um SELECT por objeto | 21 | 101 | 200 | 983 | 1.922 |
| JOIN FETCH (joinedload) | 1 | 1 | 1 | 1 | 1 |
| otimizada (projeção com JOIN) | 1 | 1 | 1 | 1 | 1 |
| SQL nativo | 1 | 1 | 1 | 1 | 1 |

### Tempo no servidor (ms, mediana), conforme a quantidade de empréstimos da página

| estratégia | 10 | 50 | 100 | 500 | 1.000 |
|---|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 9,4 | 36,7 | 72,2 | 350,3 | 674,6 |
| EAGER (lazy="joined") | 1,5 | 2,3 | 3,3 | 11,9 | 24,6 |
| EAGER com SELECT ... IN | 2,5 | 3,7 | 5,9 | 19,5 | 37,7 |
| EAGER imediato, um SELECT por objeto | 9,5 | 38,5 | 74,1 | 356,9 | 711,9 |
| JOIN FETCH (joinedload) | 1,5 | 2,3 | 3,3 | 12,6 | 23,5 |
| otimizada (projeção com JOIN) | 1,4 | 1,6 | 1,9 | 5,0 | 8,6 |
| SQL nativo | 1,1 | 1,4 | 1,7 | 4,1 | 8,3 |

### Detalhe por quantidade

#### 10 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 21 | 30 | 5,2 | 2,3 | 4,41 | 9,40 |
| EAGER (lazy="joined") | 1 | 10 | 5,2 | 2,3 | 0,58 | 1,50 |
| EAGER com SELECT ... IN | 3 | 30 | 5,2 | 2,3 | 0,79 | 2,50 |
| EAGER imediato, um SELECT por objeto | 21 | 30 | 5,2 | 2,3 | 4,33 | 9,49 |
| JOIN FETCH (joinedload) | 1 | 10 | 5,2 | 2,3 | 0,57 | 1,54 |
| otimizada (projeção com JOIN) | 1 | 10 | 1,1 | 2,3 | 0,53 | 1,38 |
| SQL nativo | 1 | 10 | 1,1 | 2,3 | 0,52 | 1,13 |

#### 50 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 101 | 150 | 26,3 | 11,4 | 16,72 | 36,73 |
| EAGER (lazy="joined") | 1 | 50 | 26,3 | 11,4 | 0,83 | 2,27 |
| EAGER com SELECT ... IN | 3 | 150 | 26,3 | 11,4 | 1,17 | 3,70 |
| EAGER imediato, um SELECT por objeto | 101 | 150 | 26,3 | 11,4 | 16,58 | 38,45 |
| JOIN FETCH (joinedload) | 1 | 50 | 26,3 | 11,4 | 0,78 | 2,26 |
| otimizada (projeção com JOIN) | 1 | 50 | 5,4 | 11,4 | 0,67 | 1,65 |
| SQL nativo | 1 | 50 | 5,4 | 11,4 | 0,65 | 1,39 |

#### 100 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 200 | 299 | 52,1 | 22,8 | 32,48 | 72,21 |
| EAGER (lazy="joined") | 1 | 100 | 52,5 | 22,8 | 1,09 | 3,31 |
| EAGER com SELECT ... IN | 3 | 299 | 52,1 | 22,8 | 2,00 | 5,86 |
| EAGER imediato, um SELECT por objeto | 200 | 299 | 52,1 | 22,8 | 31,59 | 74,07 |
| JOIN FETCH (joinedload) | 1 | 100 | 52,5 | 22,8 | 1,08 | 3,33 |
| otimizada (projeção com JOIN) | 1 | 100 | 10,8 | 22,8 | 0,83 | 1,89 |
| SQL nativo | 1 | 100 | 10,8 | 22,8 | 0,83 | 1,74 |

#### 500 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 983 | 1.482 | 259,3 | 114,2 | 153,79 | 350,34 |
| EAGER (lazy="joined") | 1 | 500 | 262,8 | 114,2 | 4,46 | 11,93 |
| EAGER com SELECT ... IN | 3 | 1.482 | 259,3 | 114,2 | 6,55 | 19,51 |
| EAGER imediato, um SELECT por objeto | 983 | 1.482 | 259,3 | 114,2 | 150,90 | 356,95 |
| JOIN FETCH (joinedload) | 1 | 500 | 262,8 | 114,2 | 4,46 | 12,61 |
| otimizada (projeção com JOIN) | 1 | 500 | 54,1 | 114,2 | 2,54 | 4,95 |
| SQL nativo | 1 | 500 | 54,1 | 114,2 | 2,08 | 4,07 |

#### 1.000 empréstimos por página

| estratégia | consultas SQL | linhas lidas do banco | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---|---:|---:|---:|---:|---:|---:|
| LAZY (lazy="select") | 1.922 | 2.921 | 512,4 | 228,3 | 295,79 | 674,57 |
| EAGER (lazy="joined") | 1 | 1.000 | 526,0 | 228,3 | 8,24 | 24,59 |
| EAGER com SELECT ... IN | 5 | 2.921 | 512,4 | 228,3 | 12,64 | 37,67 |
| EAGER imediato, um SELECT por objeto | 1.922 | 2.921 | 512,4 | 228,3 | 297,01 | 711,85 |
| JOIN FETCH (joinedload) | 1 | 1.000 | 526,0 | 228,3 | 7,78 | 23,48 |
| otimizada (projeção com JOIN) | 1 | 1.000 | 108,1 | 228,3 | 4,77 | 8,57 |
| SQL nativo | 1 | 1.000 | 108,1 | 228,3 | 4,55 | 8,27 |

### Resposta que não usa livro nem leitor (versões "resumo")

| empréstimos | mapeamento | consultas SQL | KB lidos do banco | KB da resposta | tempo no banco (ms) | tempo no servidor (ms) |
|---:|---|---:|---:|---:|---:|---:|
| 20 | LAZY | 1 | 1,2 | 3,0 | 0,32 | 1,14 |
| 20 | EAGER | 1 | 10,5 | 3,0 | 0,66 | 1,72 |
| 1.000 | LAZY | 1 | 60,9 | 151,7 | 0,90 | 5,90 |
| 1.000 | EAGER | 1 | 526,0 | 151,7 | 7,94 | 22,22 |

### Histórico de empréstimos de um leitor (planos em resultados/planos/)

| situação | leitor (empréstimos) | operações em emprestimo | ordenação (Sort) | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---|---|---:|---:|---:|---:|
| 1. sem índice | 150 (58) | Sort → Parallel Seq Scan emprestimo | sim | 299.942 | 35,221 | 225,89 | 227,18 |
| 1. sem índice | 4322 (243) | Sort → Parallel Seq Scan emprestimo | sim | 299.756 | 51,852 | 212,85 | 214,82 |
| 2. índice só em leitor_id | 150 (58) | Sort → Index Scan idx_emprestimo_leitor | sim | 0 | 0,381 | 155,90 | 157,26 |
| 2. índice só em leitor_id | 4322 (243) | Sort → Index Scan idx_emprestimo_leitor | sim | 0 | 1,231 | 159,57 | 161,27 |
| 3. índice (leitor_id, data_emprestimo DESC) | 150 (58) | Index Scan idx_emprestimo_leitor_data | não | 0 | 0,347 | 156,88 | 158,17 |
| 3. índice (leitor_id, data_emprestimo DESC) | 4322 (243) | Index Scan idx_emprestimo_leitor_data | não | 0 | 1,127 | 159,19 | 160,89 |
| 4. índice proposto + random_page_cost 4 | 150 (58) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 0,402 | – | – |
| 4. índice proposto + random_page_cost 4 | 4322 (243) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 1,511 | – | – |
| 5. índice proposto + LIMIT 10 | 150 (58) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,113 | 155,72 | 156,96 |
| 5. índice proposto + LIMIT 10 | 4322 (243) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,115 | 155,94 | 157,18 |

### Tamanho dos índices da tabela emprestimo (com os três índices do experimento criados)

| índice | colunas | tamanho |
|---|---|---:|
| emprestimo_pkey | (id) | 6,4 MB |
| idx_emprestimo_em_aberto | (data_prevista) WHERE (data_devolucao IS NULL) | 48 KB |
| idx_emprestimo_leitor | (leitor_id) | 2,2 MB |
| idx_emprestimo_leitor_data | (leitor_id, data_emprestimo DESC) | 9,0 MB |
| idx_emprestimo_livro | (livro_id) | 2,4 MB |

### Custo de escrita: inserir 20.000 empréstimos (desfeito com ROLLBACK), mediana de 5

| índices extras | índices existentes | tamanho dos índices | tempo (ms) | µs por linha |
|---|---|---:|---:|---:|
| nenhum índice do experimento | emprestimo_pkey, idx_emprestimo_livro | 8,9 MB | 851 | 42,5 |
| (leitor_id, data_emprestimo DESC) | emprestimo_pkey, idx_emprestimo_leitor_data, idx_emprestimo_livro | 17,9 MB | 1.224 | 61,2 |
| os três índices do experimento | emprestimo_pkey, idx_emprestimo_em_aberto, idx_emprestimo_leitor, idx_emprestimo_leitor_data, idx_emprestimo_livro | 20,1 MB | 1.693 | 84,6 |

### Busca por intervalo: 50 empréstimos atrasados mais antigos

| situação | operações em emprestimo | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---:|---:|---:|---:|
| sem índice parcial | Limit → Sort → Parallel Seq Scan emprestimo → Index Scan leitor_pkey | 299.100 | 33,622 | 190,26 | 191,64 |
| com índice parcial (em aberto) | Limit → Incremental Sort → Index Scan idx_emprestimo_em_aberto → Index Scan leitor_pkey | 0 | 0,817 | 157,97 | 159,50 |

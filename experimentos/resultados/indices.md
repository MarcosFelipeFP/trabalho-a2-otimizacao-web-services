### Histórico de empréstimos de um leitor (planos em resultados/planos/)

| situação | leitor (empréstimos) | operações em emprestimo | ordenação (Sort) | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---|---|---:|---:|---:|---:|
| 1. sem índice | 150 (58) | Sort → Parallel Seq Scan emprestimo | sim | 299.942 | 8,779 | 9,63 | 10,87 |
| 1. sem índice | 4322 (243) | Sort → Parallel Seq Scan emprestimo | sim | 299.756 | 9,706 | 10,32 | 12,06 |
| 2. índice só em leitor_id | 150 (58) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor | sim | 0 | 0,102 | 0,55 | 1,45 |
| 2. índice só em leitor_id | 4322 (243) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor | sim | 0 | 0,441 | 0,93 | 2,15 |
| 3. índice (leitor_id, data_emprestimo DESC) | 150 (58) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 0,103 | 0,54 | 1,44 |
| 3. índice (leitor_id, data_emprestimo DESC) | 4322 (243) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 0,462 | 0,95 | 2,20 |
| 4. índice proposto + random_page_cost 1,1 | 150 (58) | Index Scan idx_emprestimo_leitor_data | não | 0 | 0,075 | – | – |
| 4. índice proposto + random_page_cost 1,1 | 4322 (243) | Index Scan idx_emprestimo_leitor_data | não | 0 | 0,279 | – | – |
| 5. índice proposto + LIMIT 10 | 150 (58) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,025 | 0,45 | 1,28 |
| 5. índice proposto + LIMIT 10 | 4322 (243) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,027 | 0,44 | 1,24 |

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
| nenhum índice do experimento | emprestimo_pkey, idx_emprestimo_livro | 8,9 MB | 214 | 10,7 |
| (leitor_id, data_emprestimo DESC) | emprestimo_pkey, idx_emprestimo_leitor_data, idx_emprestimo_livro | 17,9 MB | 264 | 13,2 |
| os três índices do experimento | emprestimo_pkey, idx_emprestimo_em_aberto, idx_emprestimo_leitor, idx_emprestimo_leitor_data, idx_emprestimo_livro | 20,1 MB | 299 | 14,9 |

### Busca por intervalo: 50 empréstimos atrasados mais antigos

| situação | operações em emprestimo | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---:|---:|---:|---:|
| sem índice parcial | Limit → Sort → Parallel Seq Scan emprestimo → Index Scan leitor_pkey | 299.100 | 9,133 | 9,93 | 11,24 |
| com índice parcial (em aberto) | Limit → Incremental Sort → Index Scan idx_emprestimo_em_aberto → Index Scan leitor_pkey | 0 | 0,228 | 0,73 | 1,73 |

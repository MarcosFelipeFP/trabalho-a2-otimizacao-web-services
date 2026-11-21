### Histórico de empréstimos de um leitor (planos em resultados/planos/)

| situação | leitor (empréstimos) | operações em emprestimo | ordenação (Sort) | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---|---|---:|---:|---:|---:|
| 1. sem índice | 150 (58) | Sort → Parallel Seq Scan emprestimo | sim | 299.942 | 21,930 | 182,44 | 183,78 |
| 1. sem índice | 4322 (243) | Sort → Parallel Seq Scan emprestimo | sim | 299.756 | 22,764 | 184,18 | 185,95 |
| 2. índice só em leitor_id | 150 (58) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor | sim | 0 | 0,387 | 160,47 | 161,77 |
| 2. índice só em leitor_id | 4322 (243) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor | sim | 0 | 1,308 | 165,63 | 167,35 |
| 3. índice (leitor_id, data_emprestimo DESC) | 150 (58) | Index Scan idx_emprestimo_leitor_data | não | 0 | 0,332 | 161,23 | 162,70 |
| 3. índice (leitor_id, data_emprestimo DESC) | 4322 (243) | Index Scan idx_emprestimo_leitor_data | não | 0 | 1,103 | 163,90 | 165,61 |
| 4. índice proposto + random_page_cost 4 | 150 (58) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 0,407 | – | – |
| 4. índice proposto + random_page_cost 4 | 4322 (243) | Sort → Bitmap Heap Scan emprestimo → Bitmap Index Scan idx_emprestimo_leitor_data | sim | 0 | 1,495 | – | – |
| 5. índice proposto + LIMIT 10 | 150 (58) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,107 | 160,73 | 161,94 |
| 5. índice proposto + LIMIT 10 | 4322 (243) | Limit → Index Scan idx_emprestimo_leitor_data | não | 0 | 0,111 | 160,22 | 161,50 |

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
| nenhum índice do experimento | emprestimo_pkey, idx_emprestimo_livro | 8,9 MB | 655 | 32,8 |
| (leitor_id, data_emprestimo DESC) | emprestimo_pkey, idx_emprestimo_leitor_data, idx_emprestimo_livro | 17,9 MB | 749 | 37,5 |
| os três índices do experimento | emprestimo_pkey, idx_emprestimo_em_aberto, idx_emprestimo_leitor, idx_emprestimo_leitor_data, idx_emprestimo_livro | 20,1 MB | 837 | 41,9 |

### Busca por intervalo: 50 empréstimos atrasados mais antigos

| situação | operações em emprestimo | linhas descartadas pelo filtro | execução no banco (ms) | tempo no banco pela API (ms) | tempo no servidor (ms) |
|---|---|---:|---:|---:|---:|
| sem índice parcial | Limit → Sort → Parallel Seq Scan emprestimo → Index Scan leitor_pkey | 299.100 | 23,072 | 183,98 | 185,46 |
| com índice parcial (em aberto) | Limit → Incremental Sort → Index Scan idx_emprestimo_em_aberto → Index Scan leitor_pkey | 0 | 0,781 | 162,58 | 164,02 |

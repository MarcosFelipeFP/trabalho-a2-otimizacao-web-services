-- EAGER com SELECT ... IN: GET /api/emprestimos/eager-selectin?desde_id=150000&quantidade=3
-- 3 comandos, 9 linhas e 1603 bytes devolvidos pelo banco

-- 1) 3 linha(s), 6 colunas, 186 bytes; parâmetros: {'id_1': 150000, 'param_1': 3}
SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.data_devolucao 
FROM emprestimo 
WHERE emprestimo.id >= %(id_1)s::INTEGER ORDER BY emprestimo.id 
 LIMIT %(param_1)s::INTEGER;

-- 2) 3 linha(s), 4 colunas, 184 bytes; parâmetros: {'primary_keys_1': 8581, 'primary_keys_2': 7635, 'primary_keys_3': 53}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em 
FROM leitor 
WHERE leitor.id IN (%(primary_keys_1)s::INTEGER, %(primary_keys_2)s::INTEGER, %(primary_keys_3)s::INTEGER);

-- 3) 3 linha(s), 12 colunas, 1233 bytes; parâmetros: {'primary_keys_1': 13400, 'primary_keys_2': 3487, 'primary_keys_3': 10307}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em 
FROM livro 
WHERE livro.id IN (%(primary_keys_1)s::INTEGER, %(primary_keys_2)s::INTEGER, %(primary_keys_3)s::INTEGER);


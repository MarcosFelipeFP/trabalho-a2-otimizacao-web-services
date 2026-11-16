-- EAGER imediato, um SELECT por objeto: GET /api/emprestimos/eager-immediate?desde_id=150000&quantidade=3
-- 7 comandos, 9 linhas e 1603 bytes devolvidos pelo banco

-- 1) 3 linha(s), 6 colunas, 186 bytes; parâmetros: {'id_1': 150000, 'param_1': 3}
SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.data_devolucao 
FROM emprestimo 
WHERE emprestimo.id >= %(id_1)s::INTEGER ORDER BY emprestimo.id 
 LIMIT %(param_1)s::INTEGER;

-- 2) 1 linha(s), 4 colunas, 68 bytes; parâmetros: {'pk_1': 8581}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 3) 1 linha(s), 4 colunas, 62 bytes; parâmetros: {'pk_1': 7635}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 4) 1 linha(s), 4 colunas, 54 bytes; parâmetros: {'pk_1': 53}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 5) 1 linha(s), 12 colunas, 403 bytes; parâmetros: {'pk_1': 13400}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;

-- 6) 1 linha(s), 12 colunas, 414 bytes; parâmetros: {'pk_1': 3487}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;

-- 7) 1 linha(s), 12 colunas, 416 bytes; parâmetros: {'pk_1': 10307}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;


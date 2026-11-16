-- EAGER (lazy="joined"): GET /api/emprestimos/eager?desde_id=150000&quantidade=3
-- 1 comandos, 3 linhas e 1603 bytes devolvidos pelo banco

-- 1) 3 linha(s), 22 colunas, 1603 bytes; parâmetros: {'id_3': 150000, 'param_1': 3}
SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.data_devolucao, livro_1.id AS id_1, livro_1.titulo, livro_1.isbn, livro_1.editora, livro_1.ano_publicacao, livro_1.paginas, livro_1.sinopse, livro_1.autor_id, livro_1.categoria_id, livro_1.total_exemplares, livro_1.exemplares_disponiveis, livro_1.atualizado_em, leitor_1.id AS id_2, leitor_1.nome, leitor_1.email, leitor_1.cadastrado_em 
FROM emprestimo LEFT OUTER JOIN livro AS livro_1 ON livro_1.id = emprestimo.livro_id LEFT OUTER JOIN leitor AS leitor_1 ON leitor_1.id = emprestimo.leitor_id 
WHERE emprestimo.id >= %(id_3)s::INTEGER ORDER BY emprestimo.id 
 LIMIT %(param_1)s::INTEGER;


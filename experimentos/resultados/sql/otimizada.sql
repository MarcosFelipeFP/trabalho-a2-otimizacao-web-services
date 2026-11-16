-- otimizada (projeção com JOIN): GET /api/emprestimos/otimizada?desde_id=150000&quantidade=3
-- 1 comandos, 3 linhas e 311 bytes devolvidos pelo banco

-- 1) 3 linha(s), 8 colunas, 311 bytes; parâmetros: {'id_1': 150000, 'param_1': 3}
SELECT emprestimo.id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.data_devolucao, livro.id AS livro_id, livro.titulo, leitor.id AS leitor_id, leitor.nome 
FROM emprestimo JOIN livro ON livro.id = emprestimo.livro_id JOIN leitor ON leitor.id = emprestimo.leitor_id 
WHERE emprestimo.id >= %(id_1)s::INTEGER ORDER BY emprestimo.id 
 LIMIT %(param_1)s::INTEGER;


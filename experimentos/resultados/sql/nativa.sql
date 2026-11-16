-- SQL nativo: GET /api/emprestimos/nativa?desde_id=150000&quantidade=3
-- 1 comandos, 3 linhas e 311 bytes devolvidos pelo banco

-- 1) 3 linha(s), 8 colunas, 311 bytes; parâmetros: {'desde_id': 150000, 'quantidade': 3}
SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao,
           l.id AS livro_id, l.titulo, r.id AS leitor_id, r.nome
    FROM emprestimo e
    JOIN livro l ON l.id = e.livro_id
    JOIN leitor r ON r.id = e.leitor_id
    WHERE e.id >= %(desde_id)s
    ORDER BY e.id
    LIMIT %(quantidade)s;


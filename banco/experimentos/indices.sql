-- Índices do experimento da seção 5 (não são criados na carga inicial do banco).
-- Os mesmos comandos são executados pela rota PUT /api/laboratorio/indices/{nome}.
--
-- Consulta estudada (histórico de empréstimos de um leitor):
--
--   SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id, l.titulo
--   FROM emprestimo e JOIN livro l ON l.id = e.livro_id
--   WHERE e.leitor_id = 150
--   ORDER BY e.data_emprestimo DESC;

-- Índice proposto (rota: leitor-data): filtra pelo leitor e já entrega as linhas na ordem pedida.
CREATE INDEX idx_emprestimo_leitor_data ON emprestimo (leitor_id, data_emprestimo DESC);

-- Para comparação (rota: leitor): só a coluna do filtro.
CREATE INDEX idx_emprestimo_leitor ON emprestimo (leitor_id);

-- Busca por intervalo (rota: em-aberto): índice parcial, só com os empréstimos ainda não devolvidos.
--   SELECT ... WHERE data_devolucao IS NULL AND data_prevista < current_date ORDER BY data_prevista
CREATE INDEX idx_emprestimo_em_aberto ON emprestimo (data_prevista) WHERE data_devolucao IS NULL;

ANALYZE emprestimo;

-- Para voltar ao estado inicial:
--   DROP INDEX IF EXISTS idx_emprestimo_leitor_data, idx_emprestimo_leitor, idx_emprestimo_em_aberto;
--   ANALYZE emprestimo;

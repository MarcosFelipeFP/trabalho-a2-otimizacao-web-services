-- Índices criados depois da carga dos dados (carga mais rápida e índices mais compactos).
--
-- Só onde uma consulta da aplicação precisa deles:
--   livro(autor_id): "outros livros do autor", na ficha do livro;
--   emprestimo(livro_id): total de empréstimos do livro, também na ficha.
CREATE INDEX idx_livro_autor ON livro (autor_id);
CREATE INDEX idx_emprestimo_livro ON emprestimo (livro_id);

-- De propósito, emprestimo(leitor_id) começa SEM índice: o histórico de empréstimos de um leitor
-- é a consulta do experimento de índices (seção 5 do enunciado). Os índices do experimento estão
-- em banco/experimentos/indices.sql e também podem ser criados pela rota
-- PUT /api/laboratorio/indices/{nome}.

-- Estatísticas do otimizador e mapa de visibilidade atualizados antes do primeiro uso. Só as
-- tabelas da biblioteca: no Supabase o banco também guarda as tabelas internas do projeto.
VACUUM ANALYZE categoria, autor, livro, leitor, emprestimo;

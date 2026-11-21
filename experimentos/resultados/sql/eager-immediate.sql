-- EAGER imediato, um SELECT por objeto: GET /api/emprestimos/eager-immediate?desde_id=150000&quantidade=3
-- 7 comandos, 9 linhas e 4077 bytes devolvidos pelo banco

-- 1) 3 linha(s), 14 colunas, 314 bytes; parâmetros: {'id_1': 150000, 'param_1': 3}
SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, emprestimo.data_emprestimo, emprestimo.data_prevista, emprestimo.data_devolucao, emprestimo.canal, emprestimo.atendente, emprestimo.renovacoes, emprestimo.data_renovacao, emprestimo.multa, emprestimo.avaliacao, emprestimo.observacoes, emprestimo.registrado_em 
FROM emprestimo 
WHERE emprestimo.id >= %(id_1)s::INTEGER ORDER BY emprestimo.id 
 LIMIT %(param_1)s::INTEGER;

-- 2) 1 linha(s), 28 colunas, 305 bytes; parâmetros: {'pk_1': 8581}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em, leitor.numero_carteirinha, leitor.data_nascimento, leitor.tipo, leitor.matricula, leitor.curso, leitor.unidade, leitor.logradouro, leitor.numero, leitor.complemento, leitor.bairro, leitor.cidade, leitor.uf, leitor.cep, leitor.validade_carteirinha, leitor.situacao, leitor.limite_emprestimos, leitor.multas_pendentes, leitor.aceita_notificacoes, leitor.canal_preferido, leitor.categorias_favoritas, leitor.observacoes, leitor.foto_url, leitor.ultimo_acesso, leitor.atualizado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 3) 1 linha(s), 28 colunas, 378 bytes; parâmetros: {'pk_1': 7635}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em, leitor.numero_carteirinha, leitor.data_nascimento, leitor.tipo, leitor.matricula, leitor.curso, leitor.unidade, leitor.logradouro, leitor.numero, leitor.complemento, leitor.bairro, leitor.cidade, leitor.uf, leitor.cep, leitor.validade_carteirinha, leitor.situacao, leitor.limite_emprestimos, leitor.multas_pendentes, leitor.aceita_notificacoes, leitor.canal_preferido, leitor.categorias_favoritas, leitor.observacoes, leitor.foto_url, leitor.ultimo_acesso, leitor.atualizado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 4) 1 linha(s), 28 colunas, 308 bytes; parâmetros: {'pk_1': 53}
SELECT leitor.id, leitor.nome, leitor.email, leitor.cadastrado_em, leitor.numero_carteirinha, leitor.data_nascimento, leitor.tipo, leitor.matricula, leitor.curso, leitor.unidade, leitor.logradouro, leitor.numero, leitor.complemento, leitor.bairro, leitor.cidade, leitor.uf, leitor.cep, leitor.validade_carteirinha, leitor.situacao, leitor.limite_emprestimos, leitor.multas_pendentes, leitor.aceita_notificacoes, leitor.canal_preferido, leitor.categorias_favoritas, leitor.observacoes, leitor.foto_url, leitor.ultimo_acesso, leitor.atualizado_em 
FROM leitor 
WHERE leitor.id = %(pk_1)s::INTEGER;

-- 5) 1 linha(s), 47 colunas, 862 bytes; parâmetros: {'pk_1': 13400}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em, livro.subtitulo, livro.edicao, livro.ano_edicao, livro.local_publicacao, livro.idioma, livro.idioma_original, livro.tradutor, livro.ilustrador, livro.colecao, livro.volume, livro.formato, livro.largura_cm, livro.altura_cm, livro.espessura_cm, livro.peso_g, livro.isbn10, livro.cdd, livro.cutter, livro.assuntos, livro.publico_alvo, livro.classificacao_indicativa, livro.sumario, livro.notas, livro.url_capa, livro.codigo_barras, livro.localizacao, livro.estado_conservacao, livro.origem, livro.data_aquisicao, livro.preco_aquisicao, livro.fornecedor, livro.nota_fiscal, livro.avaliacao_media, livro.total_avaliacoes, livro.cadastrado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;

-- 6) 1 linha(s), 47 colunas, 967 bytes; parâmetros: {'pk_1': 3487}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em, livro.subtitulo, livro.edicao, livro.ano_edicao, livro.local_publicacao, livro.idioma, livro.idioma_original, livro.tradutor, livro.ilustrador, livro.colecao, livro.volume, livro.formato, livro.largura_cm, livro.altura_cm, livro.espessura_cm, livro.peso_g, livro.isbn10, livro.cdd, livro.cutter, livro.assuntos, livro.publico_alvo, livro.classificacao_indicativa, livro.sumario, livro.notas, livro.url_capa, livro.codigo_barras, livro.localizacao, livro.estado_conservacao, livro.origem, livro.data_aquisicao, livro.preco_aquisicao, livro.fornecedor, livro.nota_fiscal, livro.avaliacao_media, livro.total_avaliacoes, livro.cadastrado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;

-- 7) 1 linha(s), 47 colunas, 943 bytes; parâmetros: {'pk_1': 10307}
SELECT livro.id, livro.titulo, livro.isbn, livro.editora, livro.ano_publicacao, livro.paginas, livro.sinopse, livro.autor_id, livro.categoria_id, livro.total_exemplares, livro.exemplares_disponiveis, livro.atualizado_em, livro.subtitulo, livro.edicao, livro.ano_edicao, livro.local_publicacao, livro.idioma, livro.idioma_original, livro.tradutor, livro.ilustrador, livro.colecao, livro.volume, livro.formato, livro.largura_cm, livro.altura_cm, livro.espessura_cm, livro.peso_g, livro.isbn10, livro.cdd, livro.cutter, livro.assuntos, livro.publico_alvo, livro.classificacao_indicativa, livro.sumario, livro.notas, livro.url_capa, livro.codigo_barras, livro.localizacao, livro.estado_conservacao, livro.origem, livro.data_aquisicao, livro.preco_aquisicao, livro.fornecedor, livro.nota_fiscal, livro.avaliacao_media, livro.total_avaliacoes, livro.cadastrado_em 
FROM livro 
WHERE livro.id = %(pk_1)s::INTEGER;


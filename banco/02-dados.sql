-- Geração dos dados da biblioteca. A semente é fixa: toda criação do banco produz os mesmos
-- registros, com as datas contadas a partir do dia em que o banco é criado.
--
--   categoria       20
--   autor        5.000   ( 9 colunas)
--   livro       20.000   (79 colunas: ficha catalográfica, registro MARC, resenha e acervo)
--   leitor      10.000   (60 colunas: cadastro completo, documentos, contatos e preferências)
--   emprestimo 300.000   (39 colunas; três anos de empréstimos, os mais recentes ainda em aberto)
--
-- Alguns livros e leitores concentram mais empréstimos que outros, como numa biblioteca real.
--
-- As colunas principais (títulos, autores, leitores, datas dos empréstimos) saem de random(), com
-- a semente abaixo. As colunas descritivas (ficha catalográfica, endereço, canal do empréstimo...)
-- saem de pg_temp.sorteio, que não consome random(): acrescentar ou mudar uma delas não altera os
-- valores das colunas principais.

SELECT setseed(0.2026);

-- Dígito verificador do ISBN-13 (pesos 1 e 3 alternados).
CREATE FUNCTION pg_temp.isbn13(base text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT base || ((10 - sum(substr(base, i, 1)::int * CASE WHEN i % 2 = 1 THEN 1 ELSE 3 END) % 10) % 10)::text
    FROM generate_series(1, 12) AS i
$$;

-- ISBN-10 equivalente a um ISBN-13 começado por 978 (dígito verificador módulo 11; 10 vira X).
CREATE FUNCTION pg_temp.isbn10(isbn13 text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT substr(isbn13, 4, 9) || CASE WHEN d = 10 THEN 'X' ELSE d::text END
    FROM (SELECT (11 - sum(substr(isbn13, 3 + i, 1)::int * (11 - i)) % 11) % 11 AS d
          FROM generate_series(1, 9) AS i) AS c
$$;

-- Sorteio determinístico das colunas descritivas: um número de 0 a n - 1 tirado do md5 da chave.
CREATE FUNCTION pg_temp.sorteio(chave text, n int) RETURNS int
LANGUAGE sql IMMUTABLE AS $$
    SELECT (('x' || substr(md5(chave), 1, 8))::bit(32)::bigint % n)::int
$$;

-- Um elemento da lista, sorteado pela chave.
CREATE FUNCTION pg_temp.um_de(lista text[], chave text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT lista[1 + pg_temp.sorteio(chave, array_length(lista, 1))]
$$;

-- Nomes de pessoas, usados para autores, leitores, tradutores e ilustradores.
CREATE TEMP TABLE nomes AS
SELECT ARRAY['Ana', 'Beatriz', 'Bruna', 'Camila', 'Carla', 'Carolina', 'Clara', 'Daniela', 'Eduarda',
             'Fernanda', 'Gabriela', 'Helena', 'Isabela', 'Júlia', 'Juliana', 'Larissa', 'Laura',
             'Letícia', 'Luana', 'Lúcia', 'Manuela', 'Mariana', 'Marina', 'Natália', 'Patrícia',
             'Paula', 'Rafaela', 'Renata', 'Sofia', 'Vitória', 'André', 'Antônio', 'Arthur',
             'Bernardo', 'Bruno', 'Caio', 'Carlos', 'Daniel', 'Davi', 'Diego', 'Eduardo', 'Felipe',
             'Fernando', 'Gabriel', 'Gustavo', 'Heitor', 'Henrique', 'João', 'José', 'Leonardo',
             'Lucas', 'Luiz', 'Marcelo', 'Mateus', 'Miguel', 'Paulo', 'Pedro', 'Rafael', 'Rodrigo',
             'Thiago'] AS primeiros,
       ARRAY['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira',
             'Lima', 'Gomes', 'Costa', 'Ribeiro', 'Martins', 'Carvalho', 'Almeida', 'Lopes',
             'Soares', 'Fernandes', 'Vieira', 'Barbosa', 'Rocha', 'Dias', 'Nascimento', 'Andrade',
             'Moreira', 'Nunes', 'Marques', 'Machado', 'Mendes', 'Freitas', 'Cardoso', 'Ramos',
             'Gonçalves', 'Santana', 'Teixeira', 'Araújo', 'Pinto', 'Correia', 'Moura',
             'Cavalcanti', 'Monteiro', 'Batista', 'Campos', 'Duarte', 'Farias', 'Medeiros',
             'Castro', 'Pires', 'Miranda', 'Reis'] AS sobrenomes;

-- Categorias ---------------------------------------------------------------------------------
INSERT INTO categoria (id, nome)
SELECT ordem, nome
FROM unnest(ARRAY['Romance', 'Ficção científica', 'Fantasia', 'Suspense', 'Policial', 'Terror',
                  'Biografia', 'História', 'Filosofia', 'Ciências', 'Tecnologia', 'Economia',
                  'Psicologia', 'Poesia', 'Contos', 'Infantil', 'Juvenil', 'Quadrinhos',
                  'Viagem', 'Culinária']) WITH ORDINALITY AS c (nome, ordem);

-- Autores ------------------------------------------------------------------------------------
-- A maioria é brasileira; as nacionalidades do fim da lista são mais raras.
INSERT INTO autor (id, nome, nacionalidade, biografia, ano_nascimento, ano_falecimento,
                   cidade_natal, site, premios)
SELECT r.id,
       n.primeiros[1 + floor(r.a * array_length(n.primeiros, 1))::int] || ' ' ||
       n.sobrenomes[1 + floor(r.b * array_length(n.sobrenomes, 1))::int] || ' ' ||
       -- segundo sobrenome sempre diferente do primeiro
       n.sobrenomes[1 + (floor(r.b * array_length(n.sobrenomes, 1))::int + 1
                         + floor(r.c * (array_length(n.sobrenomes, 1) - 1))::int)
                        % array_length(n.sobrenomes, 1)],
       nac.lista[v.i_nac],
       pg_temp.um_de(bio.inicio, 'autor-bio1-' || r.id) || ' ' || pg_temp.um_de(bio.fim, 'autor-bio2-' || r.id),
       v.nascimento,
       CASE WHEN v.nascimento < 1945 AND pg_temp.sorteio('autor-falecimento-' || r.id, 10) < 7
            THEN least(v.nascimento + 55 + pg_temp.sorteio('autor-idade-' || r.id, 35), 2025) END,
       CASE WHEN v.i_nac = 1 THEN pg_temp.um_de(bio.cidades, 'autor-cidade-' || r.id)
            ELSE bio.capitais[v.i_nac] END,
       CASE WHEN pg_temp.sorteio('autor-site-' || r.id, 10) < 3 THEN 'https://autor' || r.id || '.example' END,
       CASE WHEN pg_temp.sorteio('autor-premio-' || r.id, 10) < 2
            THEN pg_temp.um_de(bio.premios, 'autor-premio2-' || r.id) END
FROM (SELECT g AS id, random() AS a, random() AS b, random() AS c, random() AS d
      FROM generate_series(1, 5000) AS g) AS r
CROSS JOIN nomes AS n
CROSS JOIN (SELECT ARRAY['Brasileira', 'Portuguesa', 'Angolana', 'Moçambicana', 'Argentina',
                         'Chilena', 'Uruguaia', 'Mexicana', 'Colombiana', 'Espanhola', 'Francesa',
                         'Italiana', 'Inglesa', 'Norte-americana', 'Japonesa'] AS lista) AS nac
CROSS JOIN (SELECT
    ARRAY['Nasceu numa família de professores e começou a escrever ainda na adolescência.',
          'Formou-se em jornalismo e trabalhou por anos em redações antes do primeiro livro.',
          'Estudou letras e dedicou boa parte da carreira ao ensino de literatura.',
          'Começou como cronista de jornal e logo passou a escrever romances.',
          'Viajou por vários países antes de se dedicar inteiramente à escrita.',
          'É pesquisador universitário e escreve sobre ciência para o grande público.',
          'Publicou os primeiros contos em revistas literárias independentes.',
          'Trabalhou como editor antes de lançar a própria obra.'] AS inicio,
    ARRAY['Seus livros foram traduzidos para diversos idiomas.',
          'Recebeu prêmios importantes pela obra de ficção.',
          'Hoje vive no interior e mantém uma rotina rigorosa de escrita.',
          'Participa com frequência de feiras e festivais literários.',
          'É conhecido pelo estilo direto e pelos personagens marcantes.',
          'Também escreve roteiros para cinema e televisão.',
          'Coordena oficinas de escrita criativa.',
          'Tem obras adotadas em escolas e universidades.'] AS fim,
    ARRAY['São Paulo', 'Rio de Janeiro', 'Salvador', 'Recife', 'Porto Alegre', 'Belo Horizonte',
          'Fortaleza', 'Curitiba', 'Belém', 'Manaus', 'Natal', 'São Luís', 'Florianópolis',
          'Goiânia', 'Maceió', 'Campinas'] AS cidades,
    -- na ordem das nacionalidades (a primeira, brasileira, usa a lista de cidades acima)
    ARRAY['', 'Lisboa', 'Luanda', 'Maputo', 'Buenos Aires', 'Santiago', 'Montevidéu',
          'Cidade do México', 'Bogotá', 'Madri', 'Paris', 'Roma', 'Londres', 'Nova York',
          'Tóquio'] AS capitais,
    ARRAY['Prêmio Pena de Ouro', 'Prêmio Nacional do Livro (finalista)', 'Prêmio Leitores do Ano',
          'Prêmio Revelação Literária', 'Prêmio Crítica Independente',
          'Medalha de Honra das Letras'] AS premios
) AS bio
CROSS JOIN LATERAL (
    SELECT 1 + floor(power(r.d, 3) * array_length(nac.lista, 1))::int AS i_nac,
           1900 + pg_temp.sorteio('autor-nascimento-' || r.id, 96) AS nascimento
) AS v;

-- Livros -------------------------------------------------------------------------------------
-- Título = substantivo + adjetivo opcional + complemento. A posição k é uma permutação de
-- 0..20.399 (7919 é primo com 20.400), então os 20.000 títulos são todos diferentes. A ficha
-- catalográfica e os dados do acervo combinam com a categoria, o autor e o ano de cada livro.
INSERT INTO livro (id, titulo, isbn, editora, ano_publicacao, paginas, sinopse, autor_id,
                   categoria_id, total_exemplares, exemplares_disponiveis,
                   subtitulo, edicao, ano_edicao, local_publicacao, idioma, idioma_original,
                   tradutor, ilustrador, colecao, volume, formato, largura_cm, altura_cm,
                   espessura_cm, peso_g, isbn10, cdd, cutter, assuntos, publico_alvo,
                   classificacao_indicativa, sumario, notas, url_capa, codigo_barras, localizacao,
                   estado_conservacao, origem, data_aquisicao, preco_aquisicao, fornecedor,
                   nota_fiscal, avaliacao_media, total_avaliacoes,
                   titulo_original, serie, numero_na_serie, doi, oclc, lccn, cdd_completa,
                   palavras_chave, resumo_ingles, tem_indice_remissivo, tem_bibliografia,
                   ilustracoes, encadernacao, papel, tiragem, reimpressao, data_lancamento,
                   preco_capa, moeda, distribuidora, direitos_autorais, tombo, setor, corredor,
                   ultima_conferencia, ultima_higienizacao, reservas_ativas, indicado_para,
                   premiacoes, resenha, registro_marc, atualizado_por)
SELECT r.id,
       CASE WHEN r.k % 40 < 20 THEN 'O ' ELSE 'A ' END
           || t.substantivos[1 + r.k % 40]
           || CASE WHEN r.k / 1200 = 0 THEN ''
                   WHEN r.k % 40 < 20 THEN ' ' || t.adj_masc[r.k / 1200]
                   ELSE ' ' || t.adj_fem[r.k / 1200] END
           || ' ' || t.complementos[1 + (r.k / 40) % 30],
       v.isbn,
       t.editoras[1 + floor(r.a * array_length(t.editoras, 1))::int],
       v.ano,
       v.paginas,
       -- quatro frases diferentes, escolhidas a partir de uma posição sorteada
       t.frases[1 + (r.f) % 16] || ' ' || t.frases[1 + (r.f + 3) % 16] || ' ' ||
       t.frases[1 + (r.f + 7) % 16] || ' ' || t.frases[1 + (r.f + 11) % 16],
       v.autor_id,
       v.categoria_id,
       r.exemplares,
       r.exemplares,
       -- ficha catalográfica
       CASE WHEN pg_temp.sorteio('livro-subtitulo-' || r.id, 10) < 4
            THEN pg_temp.um_de(f.subtitulos, 'livro-subtitulo2-' || r.id) END,
       w.edicao,
       least(v.ano + (w.edicao - 1) * (2 + pg_temp.sorteio('livro-intervalo-' || r.id, 5)), 2025),
       pg_temp.um_de(f.cidades, 'livro-local-' || r.id),
       'Português',
       w.idioma_original,
       CASE WHEN w.idioma_original <> 'Português'
            THEN pg_temp.um_de(n.primeiros, 'livro-tradutor1-' || r.id) || ' '
                 || pg_temp.um_de(n.sobrenomes, 'livro-tradutor2-' || r.id) END,
       CASE WHEN v.categoria_id IN (16, 17, 18)
            THEN pg_temp.um_de(n.primeiros, 'livro-ilustrador1-' || r.id) || ' '
                 || pg_temp.um_de(n.sobrenomes, 'livro-ilustrador2-' || r.id) END,
       w.colecao,
       CASE WHEN w.colecao IS NOT NULL THEN 1 + pg_temp.sorteio('livro-volume-' || r.id, 6) END,
       w.formato,
       CASE w.formato WHEN 'Bolso' THEN 11.0 WHEN 'Espiral' THEN 21.0 WHEN 'Capa dura' THEN 16.0
                      ELSE 14.0 + 2 * pg_temp.sorteio('livro-tamanho-' || r.id, 2) END,
       CASE w.formato WHEN 'Bolso' THEN 18.0 WHEN 'Espiral' THEN 28.0 WHEN 'Capa dura' THEN 23.0
                      ELSE 21.0 + 2 * pg_temp.sorteio('livro-tamanho-' || r.id, 2) END,
       round(v.paginas * 0.0055 + CASE w.formato WHEN 'Capa dura' THEN 0.7 ELSE 0.3 END, 1),
       round(v.paginas * 1.2 + CASE w.formato WHEN 'Capa dura' THEN 230 WHEN 'Bolso' THEN 40 ELSE 90 END),
       pg_temp.isbn10(v.isbn),
       f.cdd[v.categoria_id],
       upper(left(split_part(au.nome, ' ', 2), 1))
           || lpad(pg_temp.sorteio('livro-cutter-' || r.id, 1000)::text, 3, '0')
           || lower(left(t.substantivos[1 + r.k % 40], 1)),
       f.categorias[v.categoria_id] || '; ' || pg_temp.um_de(f.temas, 'livro-tema1-' || r.id)
           || '; ' || pg_temp.um_de(f.temas, 'livro-tema2-' || r.id),
       CASE WHEN v.categoria_id = 16 THEN 'Infantil'
            WHEN v.categoria_id = 17 THEN 'Juvenil'
            WHEN v.categoria_id BETWEEN 9 AND 13 THEN 'Acadêmico'
            ELSE 'Adulto' END,
       CASE v.categoria_id WHEN 16 THEN 'Livre' WHEN 17 THEN '12 anos' WHEN 18 THEN '14 anos'
                           WHEN 6 THEN '16 anos' ELSE 'Livre' END,
       (SELECT string_agg('Capítulo ' || i || ': '
                          || pg_temp.um_de(f.capitulos, 'livro-capitulo-' || r.id || '-' || i), '; '
                          ORDER BY i)
        FROM generate_series(1, 6 + pg_temp.sorteio('livro-capitulos-' || r.id, 7)) AS i) || '.',
       CASE WHEN pg_temp.sorteio('livro-notas-' || r.id, 10) < 5
            THEN pg_temp.um_de(f.notas, 'livro-notas2-' || r.id) END,
       'https://capas.biblioteca.example/' || v.isbn || '.jpg',
       -- acervo
       '2' || lpad(r.id::text, 12, '0'),
       'Estante ' || ((v.categoria_id - 1) * 3 + 1 + pg_temp.sorteio('livro-estante-' || r.id, 3))
           || ', prateleira ' || (1 + pg_temp.sorteio('livro-prateleira-' || r.id, 6)),
       pg_temp.um_de(f.conservacao, 'livro-conservacao-' || r.id),
       w.origem,
       least(make_date(greatest(v.ano, 2000), 1, 1) + pg_temp.sorteio('livro-aquisicao-' || r.id, 365),
             current_date - 1100),
       CASE WHEN w.origem = 'Compra'
            THEN round(25 + v.paginas * 0.09 + pg_temp.sorteio('livro-preco-' || r.id, 3000) / 100.0
                       + CASE w.formato WHEN 'Capa dura' THEN 30 ELSE 0 END, 2) END,
       CASE WHEN w.origem = 'Compra' THEN pg_temp.um_de(f.fornecedores, 'livro-fornecedor-' || r.id) END,
       CASE WHEN w.origem = 'Compra'
            THEN 'NF ' || lpad(pg_temp.sorteio('livro-nf-' || r.id, 1000000)::text, 6, '0') END,
       round(3 + pg_temp.sorteio('livro-avaliacao-' || r.id, 200) / 100.0, 2),
       pg_temp.sorteio('livro-avaliacoes-' || r.id, 500),
       -- descrição bibliográfica estendida e controle do acervo
       CASE w.idioma_original
           WHEN 'Inglês' THEN 'The ' || pg_temp.um_de(ARRAY['Silent Road', 'Lost Garden', 'Hidden Map',
               'Endless River', 'Forgotten Library', 'Broken Mirror', 'Distant Harbor', 'Golden Station'],
               'livro-original-' || r.id)
           WHEN 'Espanhol' THEN 'El ' || pg_temp.um_de(ARRAY['camino silencioso', 'jardín perdido',
               'mapa secreto', 'río sin fin', 'espejo roto', 'faro distante'], 'livro-original-' || r.id)
           WHEN 'Francês' THEN 'Le ' || pg_temp.um_de(ARRAY['chemin silencieux', 'jardin perdu',
               'miroir brisé', 'phare lointain', 'fleuve sans fin'], 'livro-original-' || r.id)
           WHEN 'Italiano' THEN 'Il ' || pg_temp.um_de(ARRAY['sentiero silenzioso', 'giardino perduto',
               'specchio rotto', 'faro lontano'], 'livro-original-' || r.id)
           WHEN 'Japonês' THEN pg_temp.um_de(ARRAY['Shizukana michi', 'Wasurerareta niwa',
               'Tooi toudai'], 'livro-original-' || r.id) END,
       CASE WHEN pg_temp.sorteio('livro-serie-' || r.id, 10) < 3
            THEN pg_temp.um_de(ARRAY['Trilogia das Estações', 'Crônicas do Vale', 'Saga dos Ventos',
                'Ciclo das Águas', 'Mistérios do Porto', 'Memórias do Sertão'], 'livro-serie2-' || r.id) END,
       CASE WHEN pg_temp.sorteio('livro-serie-' || r.id, 10) < 3
            THEN 1 + pg_temp.sorteio('livro-serie3-' || r.id, 5) END,
       CASE WHEN v.categoria_id BETWEEN 9 AND 13 THEN '10.5555/' || v.isbn END,
       'ocm' || lpad(pg_temp.sorteio('livro-oclc-' || r.id, 100000000)::text, 8, '0'),
       v.ano || lpad(pg_temp.sorteio('livro-lccn-' || r.id, 1000000)::text, 6, '0'),
       f.cdd[v.categoria_id] || lpad(pg_temp.sorteio('livro-cdd2-' || r.id, 100)::text, 2, '0'),
       lower(f.categorias[v.categoria_id]) || '; ' || pg_temp.um_de(f.temas, 'livro-chave1-' || r.id)
           || '; ' || pg_temp.um_de(f.temas, 'livro-chave2-' || r.id) || '; '
           || pg_temp.um_de(f.temas, 'livro-chave3-' || r.id) || '; ' || lower(t.substantivos[1 + r.k % 40])
           || '; ' || CASE WHEN w.idioma_original = 'Português' THEN 'literatura em língua portuguesa'
                           ELSE 'literatura traduzida' END,
       pg_temp.um_de(ARRAY['A compelling story about choices, memory and the places that shape us.',
               'An engaging narrative that follows its characters through difficult decisions.',
               'A detailed account that combines research, testimony and careful writing.',
               'A journey across landscapes and generations, told with sensitivity and humor.',
               'An accessible introduction to the subject, with examples and exercises.',
               'A collection of stories that explore family, friendship and identity.'], 'livro-resumo1-' || r.id)
           || ' ' || pg_temp.um_de(ARRAY['Readers will find vivid scenes and memorable dialogues.',
               'The edition includes notes that help classroom reading.',
               'It has become a reference for book clubs and reading circles.',
               'The author revisits themes that appear throughout the work.',
               'Critics praised its structure and the strength of its characters.'], 'livro-resumo2-' || r.id),
       v.categoria_id BETWEEN 7 AND 13 OR pg_temp.sorteio('livro-indice-' || r.id, 10) < 2,
       v.categoria_id BETWEEN 7 AND 13 OR pg_temp.sorteio('livro-bibliografia-' || r.id, 10) < 3,
       CASE WHEN v.categoria_id IN (16, 17, 18) THEN 'il. color.'
            WHEN pg_temp.sorteio('livro-ilustracoes-' || r.id, 10) < 2 THEN 'il. p&b' END,
       CASE w.formato WHEN 'Capa dura' THEN 'Capa dura' WHEN 'Espiral' THEN 'Espiral' ELSE 'Brochura' END,
       pg_temp.um_de(ARRAY['Pólen soft 80 g/m²', 'Pólen soft 80 g/m²', 'Offset 75 g/m²', 'Offset 90 g/m²',
               'Couché 115 g/m²'], 'livro-papel-' || r.id),
       1000 * (1 + pg_temp.sorteio('livro-tiragem-' || r.id, 10)),
       pg_temp.sorteio('livro-reimpressao-' || r.id, 4),
       make_date(v.ano, 1 + pg_temp.sorteio('livro-lancamento1-' || r.id, 12),
                 1 + pg_temp.sorteio('livro-lancamento2-' || r.id, 28)),
       round(29.90 + v.paginas * 0.12 + pg_temp.sorteio('livro-precocapa-' || r.id, 2000) / 100.0, 2),
       'BRL',
       pg_temp.um_de(f.fornecedores, 'livro-distribuidora-' || r.id),
       '© ' || v.ano || ' ' || au.nome || '. Todos os direitos desta edição reservados à '
           || t.editoras[1 + floor(r.a * array_length(t.editoras, 1))::int]
           || '. Proibida a reprodução total ou parcial sem autorização.',
       'TB-' || v.ano || '-' || lpad(r.id::text, 6, '0'),
       CASE WHEN v.categoria_id BETWEEN 9 AND 13 THEN 'Acervo acadêmico'
            WHEN v.categoria_id IN (16, 17) THEN 'Infantojuvenil'
            WHEN pg_temp.sorteio('livro-setor-' || r.id, 20) = 0 THEN 'Coleções especiais'
            ELSE 'Acervo geral' END,
       chr(65 + (v.categoria_id - 1) % 8) || (1 + pg_temp.sorteio('livro-corredor-' || r.id, 12)),
       current_date - pg_temp.sorteio('livro-conferencia-' || r.id, 365),
       current_date - 30 - pg_temp.sorteio('livro-higienizacao-' || r.id, 700),
       CASE WHEN pg_temp.sorteio('livro-reservas-' || r.id, 10) = 0
            THEN 1 + pg_temp.sorteio('livro-reservas2-' || r.id, 3) ELSE 0 END,
       CASE WHEN v.categoria_id BETWEEN 9 AND 13
            THEN 'Bibliografia básica de ' || pg_temp.um_de(ARRAY['Sistemas de Informação',
                'Ciência da Computação', 'Engenharia Civil', 'Direito', 'Administração', 'Psicologia',
                'História', 'Letras'], 'livro-curso1-' || r.id) || ' e complementar de '
                || pg_temp.um_de(ARRAY['Pedagogia', 'Jornalismo', 'Design', 'Medicina', 'Arquitetura e Urbanismo',
                'Ciências Contábeis'], 'livro-curso2-' || r.id) END,
       CASE WHEN pg_temp.sorteio('livro-premio-' || r.id, 20) = 0
            THEN pg_temp.um_de(ARRAY['Finalista de prêmio nacional de literatura',
                'Vencedor de prêmio de melhor romance do ano', 'Menção honrosa em concurso literário',
                'Selo de obra altamente recomendável para jovens'], 'livro-premio2-' || r.id)
                 || ' (' || least(v.ano + 1, 2025) || ')' END,
       pg_temp.um_de(ARRAY['Os leitores destacam o ritmo da narrativa e a construção cuidadosa dos personagens.',
               'A crítica elogiou a pesquisa por trás do texto e a linguagem acessível.',
               'É um dos títulos mais procurados da categoria no acervo da biblioteca.',
               'A edição traz notas explicativas que ajudam na leitura em sala de aula.',
               'O final surpreende e costuma render boas discussões no clube de leitura.',
               'É uma leitura indicada para quem começa a explorar o tema.'], 'livro-resenha1-' || r.id)
           || ' ' || pg_temp.um_de(ARRAY['A tradução foi revista para esta edição.',
               'Há trechos que pedem leitura atenta, mas a recompensa vale o esforço.',
               'Os capítulos curtos facilitam a leitura no dia a dia.',
               'O texto conversa bem com outros livros do mesmo autor no acervo.',
               'As ilustrações e os mapas ajudam a acompanhar a história.'], 'livro-resenha2-' || r.id)
           || ' ' || pg_temp.um_de(ARRAY['Recomendado pela equipe da biblioteca.',
               'Costuma ter fila de reservas no início do semestre.',
               'Faz parte das indicações do clube de leitura.',
               'Boa escolha para presentear ou para releitura.'], 'livro-resenha3-' || r.id),
       '=LDR  00000nam a2200000 a 4500' || E'\n'
           || '=001  BIB' || lpad(r.id::text, 8, '0') || E'\n'
           || '=020  ##$a' || v.isbn || E'\n'
           || '=082  04$a' || f.cdd[v.categoria_id] || '$2' || '23' || E'\n'
           || '=100  1#$a' || au.nome || '.' || E'\n'
           || '=245  10$a' || CASE WHEN r.k % 40 < 20 THEN 'O ' ELSE 'A ' END
           || t.substantivos[1 + r.k % 40]
           || CASE WHEN r.k / 1200 = 0 THEN ''
                   WHEN r.k % 40 < 20 THEN ' ' || t.adj_masc[r.k / 1200]
                   ELSE ' ' || t.adj_fem[r.k / 1200] END
           || ' ' || t.complementos[1 + (r.k / 40) % 30] || ' /$c' || au.nome || '.' || E'\n'
           || '=260  ##$a' || pg_temp.um_de(f.cidades, 'livro-local-' || r.id) || ' :$b'
           || t.editoras[1 + floor(r.a * array_length(t.editoras, 1))::int] || ',$c' || v.ano || '.' || E'\n'
           || '=300  ##$a' || v.paginas || ' p. ;$c' || CASE w.formato WHEN 'Bolso' THEN '18' ELSE '21' END
           || ' cm.' || E'\n'
           || '=650  #4$a' || f.categorias[v.categoria_id] || '.' || E'\n'
           || '=650  #4$a' || initcap(pg_temp.um_de(f.temas, 'livro-tema1-' || r.id)) || '.',
       pg_temp.um_de(ARRAY['Márcia R.', 'João P.', 'Fernanda L.', 'Ricardo S.', 'Aline M.', 'Paulo C.'],
                     'livro-atualizado-por-' || r.id)
FROM (SELECT g AS id,
             (g * 7919) % 20400 AS k,
             random() AS a, random() AS b, random() AS c, random() AS d, random() AS e,
             floor(random() * 16)::int AS f,
             1 + floor(power(random(), 2) * 5)::int AS exemplares
      FROM generate_series(1, 20000) AS g) AS r
CROSS JOIN (SELECT
    ARRAY['Silêncio', 'Segredo', 'Caminho', 'Jardim', 'Mapa', 'Retrato', 'Labirinto', 'Destino',
          'Guardião', 'Eco', 'Horizonte', 'Enigma', 'Viajante', 'Farol', 'Relógio', 'Espelho',
          'Código', 'Inventário', 'Herdeiro', 'Pacto',
          'Casa', 'Cidade', 'Memória', 'Ilha', 'Estrada', 'Carta', 'Sombra', 'Viagem', 'Promessa',
          'Herança', 'Canção', 'Fronteira', 'Noite', 'Chave', 'Travessia', 'Lenda', 'Arte',
          'Ciência', 'Biblioteca', 'Estação'] AS substantivos,
    ARRAY['Perdido', 'Esquecido', 'Secreto', 'Proibido', 'Eterno', 'Antigo', 'Dourado',
          'Silencioso', 'Invisível', 'Distante', 'Partido', 'Selvagem', 'Quebrado', 'Infinito',
          'Sombrio', 'Imperfeito'] AS adj_masc,
    ARRAY['Perdida', 'Esquecida', 'Secreta', 'Proibida', 'Eterna', 'Antiga', 'Dourada',
          'Silenciosa', 'Invisível', 'Distante', 'Partida', 'Selvagem', 'Quebrada', 'Infinita',
          'Sombria', 'Imperfeita'] AS adj_fem,
    ARRAY['do Mar', 'das Montanhas', 'do Sertão', 'do Tempo', 'dos Esquecidos', 'do Norte',
          'de Papel', 'de Vidro', 'em Chamas', 'sem Fim', 'do Rio', 'de Inverno', 'da Serra',
          'dos Ventos', 'do Deserto', 'da Floresta', 'das Estrelas', 'do Porto', 'da Lua',
          'de Outono', 'das Águas', 'do Imperador', 'da Rainha', 'do Abismo', 'de Areia',
          'dos Sonhos', 'da Aurora', 'de Sal', 'de Ferro', 'do Vale'] AS complementos,
    ARRAY['Editora Aurora', 'Casa das Letras', 'Editora Horizonte', 'Selo Ipê', 'Editora Maré',
          'Livros do Cerrado', 'Editora Atlântica', 'Pena & Tinta', 'Editora Bússola',
          'Editora Farol', 'Edições Jabuticaba', 'Editora Pampa', 'Página Nova',
          'Editora Vértice', 'Edições Caravela'] AS editoras,
    ARRAY['Uma narrativa envolvente que acompanha personagens marcados por escolhas difíceis.',
          'Entre segredos de família e reviravoltas inesperadas, a história revela o peso do passado.',
          'O autor conduz o leitor por paisagens vívidas e diálogos afiados.',
          'Uma obra premiada pela crítica, nesta edição revista e com notas inéditas.',
          'Ao longo dos capítulos, a trama alterna presente e memória com ritmo preciso.',
          'Indicado para quem procura uma leitura instigante e cheia de detalhes.',
          'A pesquisa minuciosa por trás do texto aparece em cada página.',
          'Um retrato sensível das relações humanas em tempos de mudança.',
          'Com linguagem acessível, o livro apresenta conceitos fundamentais e exemplos práticos.',
          'A edição traz prefácio, cronologia e um posfácio escrito por especialistas.',
          'Personagens inesquecíveis enfrentam dilemas que ecoam até os dias de hoje.',
          'O texto combina humor, melancolia e uma observação atenta do cotidiano.',
          'Um clássico moderno, frequentemente adotado em clubes de leitura.',
          'A cada capítulo, novas pistas desafiam o leitor a montar o quebra-cabeça.',
          'Escrito com rigor e paixão, o livro convida à reflexão sobre escolhas e consequências.',
          'Leitura recomendada para estudantes e curiosos que desejam se aprofundar no tema.'] AS frases
) AS t
CROSS JOIN (SELECT
    ARRAY['Uma história de coragem', 'Crônicas de uma cidade', 'Edição comentada',
          'Ensaios reunidos', 'Memórias de viagem', 'Guia prático', 'Contos escolhidos',
          'Uma jornada pelo tempo', 'Volume único', 'Romance', 'Diário de bordo',
          'Edição de bolso', 'Antologia', 'Uma investigação', 'Notas e reflexões',
          'Introdução ao tema'] AS subtitulos,
    ARRAY['São Paulo', 'São Paulo', 'São Paulo', 'São Paulo', 'Rio de Janeiro', 'Rio de Janeiro',
          'Rio de Janeiro', 'Porto Alegre', 'Belo Horizonte', 'Curitiba', 'Recife', 'Salvador',
          'Brasília', 'Florianópolis', 'Lisboa'] AS cidades,
    ARRAY['Clássicos de Bolso', 'Biblioteca do Leitor', 'Grandes Narrativas', 'Série Ciência Hoje',
          'Coleção Horizonte', 'Mundo Jovem', 'Pensamento Contemporâneo',
          'Literatura em Foco'] AS colecoes,
    ARRAY['Brochura', 'Brochura', 'Brochura', 'Brochura', 'Brochura', 'Brochura', 'Brochura',
          'Brochura', 'Brochura', 'Brochura', 'Brochura', 'Brochura', 'Capa dura', 'Capa dura',
          'Capa dura', 'Capa dura', 'Capa dura', 'Bolso', 'Bolso', 'Espiral'] AS formatos,
    -- classificação decimal de Dewey de cada categoria, na ordem dos ids
    ARRAY['869.3', '869.3', '869.3', '869.3', '869.3', '869.3', '920', '981', '100', '500',
          '600', '330', '150', '869.1', '869.3', '028.5', '028.5', '741.5', '910',
          '641.5'] AS cdd,
    ARRAY['Romance', 'Ficção científica', 'Fantasia', 'Suspense', 'Policial', 'Terror',
          'Biografia', 'História', 'Filosofia', 'Ciências', 'Tecnologia', 'Economia',
          'Psicologia', 'Poesia', 'Contos', 'Infantil', 'Juvenil', 'Quadrinhos', 'Viagem',
          'Culinária'] AS categorias,
    ARRAY['memória', 'família', 'identidade', 'viagem', 'amizade', 'poder', 'tecnologia',
          'natureza', 'cidade', 'tempo', 'guerra', 'amor', 'ciência', 'mistério', 'política',
          'infância', 'morte', 'liberdade', 'trabalho', 'arte', 'fé', 'exílio', 'educação',
          'sociedade', 'história do Brasil', 'ética', 'meio ambiente', 'economia', 'saúde',
          'cultura popular'] AS temas,
    ARRAY['O começo', 'A chegada', 'Primeiras descobertas', 'O encontro', 'Sombras do passado',
          'A decisão', 'Caminhos cruzados', 'O segredo revelado', 'A tempestade', 'Despedidas',
          'O retorno', 'Novas perguntas', 'A travessia', 'O pacto', 'Vozes da cidade', 'A carta',
          'O último verão', 'Mapas e territórios', 'O silêncio', 'Recomeço', 'Notas de viagem',
          'A herança', 'O arquivo', 'Linhas tortas', 'O inventário', 'A espera', 'Fragmentos',
          'O farol', 'Conclusão', 'Epílogo'] AS capitulos,
    ARRAY['Inclui índice remissivo e bibliografia.', 'Edição revista e ampliada pelo autor.',
          'Contém ilustrações em preto e branco.', 'Exemplar com dedicatória do autor.',
          'Tradução a partir da edição original, com notas do tradutor.',
          'Inclui glossário e cronologia.', 'Edição comemorativa, com prefácio inédito.',
          'Volume com mapas e caderno de fotos.'] AS notas,
    ARRAY['Novo', 'Bom', 'Bom', 'Bom', 'Bom', 'Regular', 'Regular', 'Desgastado'] AS conservacao,
    ARRAY['Compra', 'Compra', 'Compra', 'Compra', 'Compra', 'Compra', 'Compra', 'Doação',
          'Doação', 'Permuta'] AS origens,
    ARRAY['Distribuidora Leitura Viva', 'Livraria Central', 'Distribuidora Saber',
          'Livros & Companhia', 'Distribuidora Atlântico', 'Casa do Livro Técnico'] AS fornecedores
) AS f
CROSS JOIN nomes AS n
CROSS JOIN LATERAL (
    SELECT pg_temp.isbn13('978' || lpad(((r.id::bigint * 104729) % 1000000000)::text, 9, '0')) AS isbn,
           1950 + floor((1 - power(r.b, 2)) * 76)::int AS ano,
           64 + floor(r.c * 640)::int AS paginas,
           1 + floor(r.d * 5000)::int AS autor_id,
           1 + floor(r.e * 20)::int AS categoria_id
) AS v
CROSS JOIN LATERAL (SELECT nome, nacionalidade FROM autor WHERE autor.id = v.autor_id) AS au
CROSS JOIN LATERAL (
    SELECT CASE WHEN s.edicao < 600 THEN 1 WHEN s.edicao < 850 THEN 2 WHEN s.edicao < 950 THEN 3
                ELSE 4 + s.edicao % 5 END AS edicao,
           CASE au.nacionalidade
               WHEN 'Brasileira' THEN 'Português' WHEN 'Portuguesa' THEN 'Português'
               WHEN 'Angolana' THEN 'Português' WHEN 'Moçambicana' THEN 'Português'
               WHEN 'Francesa' THEN 'Francês' WHEN 'Italiana' THEN 'Italiano'
               WHEN 'Inglesa' THEN 'Inglês' WHEN 'Norte-americana' THEN 'Inglês'
               WHEN 'Japonesa' THEN 'Japonês'
               ELSE 'Espanhol' END AS idioma_original,
           CASE WHEN pg_temp.sorteio('livro-colecao-' || r.id, 10) < 2
                THEN pg_temp.um_de(f.colecoes, 'livro-colecao2-' || r.id) END AS colecao,
           pg_temp.um_de(f.formatos, 'livro-formato-' || r.id) AS formato,
           pg_temp.um_de(f.origens, 'livro-origem-' || r.id) AS origem
    FROM (SELECT pg_temp.sorteio('livro-edicao-' || r.id, 1000) AS edicao) AS s
) AS w;

-- Leitores -----------------------------------------------------------------------------------
-- Todos se cadastraram há mais de três anos, antes do primeiro empréstimo gerado.
INSERT INTO leitor (id, nome, email, cadastrado_em, numero_carteirinha, data_nascimento, tipo,
                    matricula, curso, unidade, logradouro, numero, complemento, bairro, cidade, uf,
                    cep, validade_carteirinha, situacao, limite_emprestimos, multas_pendentes,
                    aceita_notificacoes, canal_preferido, categorias_favoritas, observacoes,
                    foto_url, ultimo_acesso, atualizado_em,
                    nome_social, cpf, rg, orgao_emissor, genero, estado_civil, nacionalidade,
                    naturalidade, telefone, celular, email_alternativo, escolaridade, profissao,
                    empresa, contato_emergencia, telefone_emergencia, necessidades_especiais,
                    idioma_preferido, formato_preferido, recebe_newsletter, termos_aceitos_em,
                    versao_termos, origem_cadastro, pontos_fidelidade, nivel_fidelidade,
                    bloqueado_ate, motivo_bloqueio, senha_hash, token_sessao,
                    preferencias_notificacao, interesses, ultimo_ip)
SELECT r.id,
       p.primeiro || ' ' || p.sobrenome || ' ' || p.sobrenome2,
       lower(translate(p.primeiro || '.' || p.sobrenome,
                       'áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ', 'aaaaeeiooouucAAAAEEIOOOUUC'))
           || r.id || '@email.example',
       q.cadastro,
       'BIB' || lpad(r.id::text, 7, '0'),
       (current_date - make_interval(years => 17 + pg_temp.sorteio('leitor-idade-' || r.id, 55)))::date
           - pg_temp.sorteio('leitor-aniversario-' || r.id, 365),
       q.tipo,
       CASE WHEN q.tipo <> 'Comunidade'
            THEN (2015 + pg_temp.sorteio('leitor-ingresso-' || r.id, 10))::text
                 || lpad(pg_temp.sorteio('leitor-matricula-' || r.id, 1000000)::text, 6, '0') END,
       CASE WHEN q.tipo IN ('Aluno', 'Professor') THEN pg_temp.um_de(cad.cursos, 'leitor-curso-' || r.id) END,
       CASE WHEN q.tipo = 'Comunidade' THEN 'Biblioteca Comunitária'
            ELSE pg_temp.um_de(cad.unidades, 'leitor-unidade-' || r.id) END,
       pg_temp.um_de(cad.tipos_logradouro, 'leitor-logradouro1-' || r.id) || ' '
           || pg_temp.um_de(cad.logradouros, 'leitor-logradouro2-' || r.id),
       (1 + pg_temp.sorteio('leitor-numero-' || r.id, 2500))::text,
       CASE WHEN pg_temp.sorteio('leitor-complemento-' || r.id, 10) < 4
            THEN 'Apto ' || (101 + pg_temp.sorteio('leitor-apto-' || r.id, 1200)) END,
       pg_temp.um_de(cad.bairros, 'leitor-bairro-' || r.id),
       pg_temp.um_de(cad.cidades, 'leitor-cidade-' || r.id),
       'RJ',
       lpad((20000000 + pg_temp.sorteio('leitor-cep-' || r.id, 8999999))::text, 8, '0'),
       current_date - 120 + pg_temp.sorteio('leitor-validade-' || r.id, 720),
       q.situacao,
       CASE q.tipo WHEN 'Professor' THEN 10 WHEN 'Comunidade' THEN 3 ELSE 5 END,
       CASE WHEN q.situacao = 'Suspenso'
            THEN round(2 + pg_temp.sorteio('leitor-multa-' || r.id, 8000) / 100.0, 2) ELSE 0 END,
       pg_temp.sorteio('leitor-notificacoes-' || r.id, 10) < 8,
       pg_temp.um_de(cad.canais, 'leitor-canal-' || r.id),
       pg_temp.um_de(cad.categorias, 'leitor-favorita1-' || r.id) || ', '
           || pg_temp.um_de(cad.categorias, 'leitor-favorita2-' || r.id),
       CASE WHEN pg_temp.sorteio('leitor-observacoes-' || r.id, 10) = 0
            THEN pg_temp.um_de(cad.observacoes, 'leitor-observacoes2-' || r.id) END,
       'https://fotos.biblioteca.example/leitores/' || r.id || '.jpg',
       (current_date - pg_temp.sorteio('leitor-acesso-' || r.id, 90))
           + make_interval(mins => 480 + pg_temp.sorteio('leitor-acesso2-' || r.id, 840)),
       q.cadastro + make_interval(days => pg_temp.sorteio('leitor-atualizado-' || r.id, 900)),
       -- documentos, contatos e preferências
       CASE WHEN pg_temp.sorteio('leitor-nome-social-' || r.id, 100) = 0
            THEN pg_temp.um_de(n.primeiros, 'leitor-nome-social2-' || r.id) || ' ' || p.sobrenome END,
       lpad(pg_temp.sorteio('leitor-cpf-' || r.id, 1000000000)::text, 9, '0')
           || lpad(pg_temp.sorteio('leitor-cpf-dv-' || r.id, 100)::text, 2, '0'),
       lpad(pg_temp.sorteio('leitor-rg1-' || r.id, 100)::text, 2, '0') || '.'
           || lpad(pg_temp.sorteio('leitor-rg2-' || r.id, 1000)::text, 3, '0') || '.'
           || lpad(pg_temp.sorteio('leitor-rg3-' || r.id, 1000)::text, 3, '0') || '-'
           || pg_temp.sorteio('leitor-rg4-' || r.id, 10),
       pg_temp.um_de(ARRAY['DETRAN-RJ', 'DETRAN-RJ', 'IFP-RJ', 'SSP-SP', 'SSP-MG'], 'leitor-orgao-' || r.id),
       pg_temp.um_de(ARRAY['Feminino', 'Masculino', 'Feminino', 'Masculino', 'Não informado'],
                     'leitor-genero-' || r.id),
       pg_temp.um_de(ARRAY['Solteiro(a)', 'Solteiro(a)', 'Solteiro(a)', 'Casado(a)', 'Casado(a)',
                           'Divorciado(a)'], 'leitor-estado-civil-' || r.id),
       'Brasileira',
       pg_temp.um_de(cad.cidades, 'leitor-naturalidade-' || r.id) || ' (RJ)',
       '(21) ' || (2000 + pg_temp.sorteio('leitor-telefone1-' || r.id, 8000)) || '-'
           || lpad(pg_temp.sorteio('leitor-telefone2-' || r.id, 10000)::text, 4, '0'),
       '(21) 9' || (8000 + pg_temp.sorteio('leitor-celular1-' || r.id, 2000)) || '-'
           || lpad(pg_temp.sorteio('leitor-celular2-' || r.id, 10000)::text, 4, '0'),
       CASE WHEN pg_temp.sorteio('leitor-email2-' || r.id, 2) = 0
            THEN lower(translate(p.primeiro || p.sobrenome2,
                                 'áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ', 'aaaaeeiooouucAAAAEEIOOOUUC'))
                 || r.id || '@correio.example' END,
       CASE q.tipo WHEN 'Aluno' THEN 'Superior incompleto'
                   WHEN 'Professor' THEN pg_temp.um_de(ARRAY['Mestrado', 'Doutorado', 'Doutorado'],
                                                       'leitor-escolaridade-' || r.id)
                   ELSE pg_temp.um_de(ARRAY['Ensino médio completo', 'Superior completo', 'Superior incompleto',
                                            'Pós-graduação'], 'leitor-escolaridade-' || r.id) END,
       CASE q.tipo WHEN 'Aluno' THEN 'Estudante' WHEN 'Professor' THEN 'Professor universitário'
                   ELSE pg_temp.um_de(ARRAY['Analista administrativo', 'Enfermeira', 'Engenheiro', 'Comerciante',
                                            'Aposentado', 'Designer', 'Advogada', 'Técnico em informática'],
                                      'leitor-profissao-' || r.id) END,
       CASE WHEN q.tipo IN ('Funcionário', 'Comunidade') AND pg_temp.sorteio('leitor-empresa-' || r.id, 3) < 2
            THEN pg_temp.um_de(ARRAY['Universidade Atlântica', 'Hospital Santa Clara', 'Mercado Bom Preço',
                                     'Prefeitura Municipal', 'Construtora Horizonte'], 'leitor-empresa2-' || r.id) END,
       pg_temp.um_de(n.primeiros, 'leitor-emergencia1-' || r.id) || ' ' || p.sobrenome || ' ('
           || pg_temp.um_de(ARRAY['mãe', 'pai', 'irmã', 'irmão', 'cônjuge', 'amiga'], 'leitor-emergencia2-' || r.id)
           || ')',
       '(21) 9' || (8000 + pg_temp.sorteio('leitor-emergencia3-' || r.id, 2000)) || '-'
           || lpad(pg_temp.sorteio('leitor-emergencia4-' || r.id, 10000)::text, 4, '0'),
       CASE WHEN pg_temp.sorteio('leitor-necessidades-' || r.id, 50) = 0
            THEN pg_temp.um_de(ARRAY['Baixa visão: prefere livros em fonte ampliada.',
                                     'Usa cadeira de rodas: retirada no térreo.',
                                     'Usa leitor de tela no catálogo on-line.'], 'leitor-necessidades2-' || r.id) END,
       'Português',
       pg_temp.um_de(ARRAY['Impresso', 'Impresso', 'Impresso', 'E-book', 'Audiolivro'], 'leitor-formato-' || r.id),
       pg_temp.sorteio('leitor-newsletter-' || r.id, 10) < 6,
       q.cadastro + time '10:00' + make_interval(mins => pg_temp.sorteio('leitor-termos-' || r.id, 480)),
       pg_temp.um_de(ARRAY['v2.0', 'v2.1', 'v3.0', 'v3.2'], 'leitor-versao-termos-' || r.id),
       pg_temp.um_de(ARRAY['Balcão', 'Balcão', 'Site', 'Aplicativo'], 'leitor-origem-' || r.id),
       pg_temp.sorteio('leitor-pontos-' || r.id, 5000),
       CASE WHEN pg_temp.sorteio('leitor-pontos-' || r.id, 5000) >= 4000 THEN 'Ouro'
            WHEN pg_temp.sorteio('leitor-pontos-' || r.id, 5000) >= 2000 THEN 'Prata' ELSE 'Bronze' END,
       CASE WHEN q.situacao = 'Suspenso' THEN current_date + 1 + pg_temp.sorteio('leitor-bloqueio-' || r.id, 30) END,
       CASE WHEN q.situacao = 'Suspenso'
            THEN 'Multa pendente por atraso na devolução; regularizar no balcão ou pelo aplicativo.' END,
       '$2b$12$' || left(translate(encode(decode(md5('leitor-senha-' || r.id) || md5('leitor-sal-' || r.id)
                                                 || md5('leitor-custo-' || r.id), 'hex'), 'base64'), '+/', './'), 53),
       CASE WHEN pg_temp.sorteio('leitor-sessao-' || r.id, 10) < 4
            THEN md5('leitor-sessao1-' || r.id) || md5('leitor-sessao2-' || r.id) END,
       'Novidades: ' || CASE WHEN pg_temp.sorteio('leitor-newsletter-' || r.id, 10) < 6 THEN 'sim' ELSE 'não' END
           || '; lembretes: ' || lower(pg_temp.um_de(cad.canais, 'leitor-canal-' || r.id))
           || '; reservas: ' || lower(pg_temp.um_de(cad.canais, 'leitor-canal-reservas-' || r.id)),
       'Gosta de ' || lower(pg_temp.um_de(cad.categorias, 'leitor-favorita1-' || r.id)) || ' e '
           || lower(pg_temp.um_de(cad.categorias, 'leitor-favorita2-' || r.id)) || '. '
           || pg_temp.um_de(ARRAY['Costuma ler à noite e prefere edições de bolso.',
                                  'Acompanha os lançamentos e faz reservas com antecedência.',
                                  'Lê principalmente para os trabalhos da faculdade.',
                                  'Participa das rodas de leitura aos sábados.',
                                  'Prefere autores brasileiros contemporâneos.',
                                  'Pede indicações aos bibliotecários com frequência.'], 'leitor-interesses-' || r.id),
       '10.' || pg_temp.sorteio('leitor-ip1-' || r.id, 4) || '.' || pg_temp.sorteio('leitor-ip2-' || r.id, 256)
           || '.' || (1 + pg_temp.sorteio('leitor-ip3-' || r.id, 254))
FROM (SELECT g AS id, random() AS a, random() AS b, random() AS c, random() AS d
      FROM generate_series(1, 10000) AS g) AS r
CROSS JOIN nomes AS n
CROSS JOIN (SELECT
    ARRAY['Aluno', 'Aluno', 'Aluno', 'Aluno', 'Aluno', 'Aluno', 'Professor', 'Funcionário',
          'Comunidade', 'Comunidade'] AS tipos,
    ARRAY['Sistemas de Informação', 'Ciência da Computação', 'Engenharia Civil', 'Direito',
          'Administração', 'Psicologia', 'Medicina', 'Arquitetura e Urbanismo', 'Letras',
          'História', 'Pedagogia', 'Jornalismo', 'Design', 'Enfermagem', 'Odontologia',
          'Ciências Contábeis'] AS cursos,
    ARRAY['Campus Centro', 'Campus Norte', 'Campus Sul'] AS unidades,
    ARRAY['Rua', 'Rua', 'Rua', 'Rua', 'Avenida', 'Avenida', 'Travessa', 'Alameda',
          'Estrada'] AS tipos_logradouro,
    ARRAY['das Acácias', 'dos Ipês', 'da Primavera', 'São João', 'Sete de Setembro', 'das Flores',
          'do Comércio', 'Santa Luzia', 'Boa Vista', 'dos Andradas', 'Tiradentes', 'das Palmeiras',
          'do Mercado', 'Bela Vista', 'das Laranjeiras', 'Barão do Rio Branco',
          'Marechal Deodoro', 'da Praia', 'do Sol', 'Nova Esperança'] AS logradouros,
    ARRAY['Centro', 'Jardim América', 'Vila Nova', 'Santa Rosa', 'Boa Vista', 'São José',
          'Parque das Flores', 'Jardim Primavera', 'Vila Real', 'Alto da Serra', 'Bela Vista',
          'Liberdade', 'Santa Teresa', 'Jardim Botânico', 'Vila Isabel', 'Fonseca'] AS bairros,
    ARRAY['Rio de Janeiro', 'Rio de Janeiro', 'Rio de Janeiro', 'Rio de Janeiro',
          'Rio de Janeiro', 'Rio de Janeiro', 'Rio de Janeiro', 'Rio de Janeiro', 'Niterói',
          'São Gonçalo', 'Duque de Caxias', 'Nova Iguaçu', 'Petrópolis', 'Volta Redonda',
          'Campos dos Goytacazes', 'Macaé', 'Cabo Frio', 'Teresópolis'] AS cidades,
    ARRAY['E-mail', 'E-mail', 'Aplicativo', 'Aplicativo', 'SMS'] AS canais,
    ARRAY['Romance', 'Ficção científica', 'Fantasia', 'Suspense', 'Policial', 'Terror',
          'Biografia', 'História', 'Filosofia', 'Ciências', 'Tecnologia', 'Economia',
          'Psicologia', 'Poesia', 'Contos', 'Infantil', 'Juvenil', 'Quadrinhos', 'Viagem',
          'Culinária'] AS categorias,
    ARRAY['Prefere retirar livros no período da noite.',
          'Pediu aviso de chegada de novos títulos de ficção.',
          'Cadastro atualizado no último atendimento.',
          'Possui reserva recorrente de periódicos.',
          'Participa do clube de leitura mensal.',
          'Pediu livros em fonte ampliada.'] AS observacoes
) AS cad
CROSS JOIN LATERAL (
    SELECT n.primeiros[1 + floor(r.a * array_length(n.primeiros, 1))::int] AS primeiro,
           n.sobrenomes[1 + floor(r.b * array_length(n.sobrenomes, 1))::int] AS sobrenome,
           n.sobrenomes[1 + (floor(r.b * array_length(n.sobrenomes, 1))::int + 1
                             + floor(r.c * (array_length(n.sobrenomes, 1) - 1))::int)
                            % array_length(n.sobrenomes, 1)] AS sobrenome2
) AS p
CROSS JOIN LATERAL (
    SELECT current_date - (1100 + floor(r.d * 1500)::int) AS cadastro,
           pg_temp.um_de(cad.tipos, 'leitor-tipo-' || r.id) AS tipo,
           CASE WHEN s.situacao < 17 THEN 'Ativo' WHEN s.situacao < 19 THEN 'Suspenso'
                ELSE 'Inativo' END AS situacao
    FROM (SELECT pg_temp.sorteio('leitor-situacao-' || r.id, 20) AS situacao) AS s
) AS q;

-- Empréstimos --------------------------------------------------------------------------------
-- Três anos de empréstimos, das 9h às 20h. Livros e leitores são sorteados com viés (potência
-- 1,3) e espalhados pelos ids com uma permutação, para os mais ativos não ficarem nos primeiros
-- ids. A devolução ocorre de 1 a 27 dias depois; se essa data não é anterior à meia-noite do dia
-- de criação do banco, o empréstimo fica em aberto (assim os dados não dependem da hora em que o
-- banco é criado). O prazo de devolução é de 14 dias. Os ids seguem a ordem cronológica. As
-- colunas de atendimento (canal, renovações, multa, avaliação) saem da posição sorteada (seq).
INSERT INTO emprestimo (id, livro_id, leitor_id, data_emprestimo, data_prevista, data_devolucao,
                        canal, atendente, renovacoes, data_renovacao, multa, avaliacao,
                        observacoes, registrado_em,
                        protocolo, unidade, balcao, terminal, codigo_exemplar, numero_exemplar,
                        estado_retirada, estado_devolucao, prazo_maximo, renovacao_online,
                        lembrete_enviado_em, lembretes_enviados, canal_lembrete, dias_atraso,
                        multa_paga, data_pagamento_multa, forma_pagamento, desconto_multa,
                        finalidade, disciplina, comentario_avaliacao, ip_origem, assinatura_termo,
                        atualizado_em, versao)
SELECT row_number() OVER (ORDER BY x.data_emprestimo, x.seq),
       x.livro_id,
       x.leitor_id,
       x.data_emprestimo,
       x.data_emprestimo::date + 14,
       CASE WHEN y.devolvido THEN x.data_emprestimo + x.duracao END,
       y.canal,
       CASE WHEN y.canal = 'Balcão' THEN a.atendentes[1 + (x.seq * 13) % array_length(a.atendentes, 1)] END,
       y.renovacoes,
       CASE WHEN y.renovacoes > 0 THEN x.data_emprestimo::date + 12 END,
       CASE WHEN y.devolvido AND y.renovacoes = 0 AND x.duracao > interval '15 days'
            THEN 1.50 * (extract(day FROM x.duracao)::int - 14) ELSE 0 END,
       CASE WHEN y.devolvido AND x.seq % 5 < 2 THEN (ARRAY[5, 4, 5, 3, 4, 5, 2, 4])[1 + (x.seq * 31) % 8] END,
       CASE WHEN x.seq % 25 = 0 THEN a.observacoes[1 + (x.seq / 25) % array_length(a.observacoes, 1)] END,
       x.data_emprestimo + make_interval(secs => x.seq % 90),
       -- atendimento, exemplar, lembretes, multa e controle do registro (aritmética sobre seq, sem
       -- random(): não muda as colunas acima)
       'EMP-' || to_char(x.data_emprestimo, 'YYYYMMDD') || '-' || lpad(x.seq::text, 6, '0'),
       (ARRAY['Campus Centro', 'Campus Centro', 'Campus Norte', 'Campus Sul',
              'Biblioteca Comunitária'])[1 + (x.seq * 3) % 5],
       CASE WHEN y.canal = 'Balcão' THEN 1 + (x.seq * 11) % 6 END,
       CASE y.canal WHEN 'Balcão' THEN 'BALCAO-0' || (1 + (x.seq * 11) % 6)
                    WHEN 'Autoatendimento' THEN 'TOTEM-0' || (1 + x.seq % 4)
                    ELSE 'APLICATIVO' END,
       '3' || lpad(x.livro_id::text, 8, '0') || lpad((1 + x.seq % 3)::text, 4, '0'),
       1 + x.seq % 3,
       (ARRAY['Novo', 'Bom', 'Bom', 'Bom', 'Regular', 'Regular'])[1 + (x.seq * 5) % 6],
       CASE WHEN y.devolvido
            THEN (ARRAY['Bom', 'Bom', 'Bom', 'Regular', 'Regular', 'Desgastado'])[1 + (x.seq * 17) % 6] END,
       x.data_emprestimo::date + 42,
       y.canal <> 'Balcão' AND x.seq % 3 = 0,
       CASE WHEN x.seq % 10 < 7 THEN x.data_emprestimo::date + 12 + time '08:00' END,
       CASE WHEN x.seq % 10 < 7 THEN 1 + (x.seq * 7) % 3 ELSE 0 END,
       CASE WHEN x.seq % 10 < 7 THEN (ARRAY['E-mail', 'E-mail', 'SMS', 'Aplicativo'])[1 + (x.seq * 3) % 4] END,
       CASE WHEN y.devolvido THEN greatest(0, extract(day FROM x.duracao)::int - 14) ELSE 0 END,
       NOT (y.devolvido AND y.renovacoes = 0 AND x.duracao > interval '15 days' AND x.seq % 4 = 0),
       CASE WHEN y.devolvido AND y.renovacoes = 0 AND x.duracao > interval '15 days' AND x.seq % 4 <> 0
            THEN (x.data_emprestimo + x.duracao)::date END,
       CASE WHEN y.devolvido AND y.renovacoes = 0 AND x.duracao > interval '15 days' AND x.seq % 4 <> 0
            THEN (ARRAY['Pix', 'Pix', 'Cartão de débito', 'Dinheiro'])[1 + (x.seq / 4) % 4] END,
       CASE WHEN y.devolvido AND y.renovacoes = 0 AND x.duracao > interval '15 days' AND x.seq % 8 = 1
            THEN 1.00 ELSE 0 END,
       (ARRAY['Lazer', 'Lazer', 'Estudo', 'Estudo', 'Pesquisa acadêmica', 'Trabalho de conclusão de curso',
              'Preparação para concurso'])[1 + (x.seq * 13) % 7],
       CASE WHEN x.seq % 2 = 0
            THEN (ARRAY['Banco de Dados', 'Cálculo I', 'Teoria Literária', 'História do Brasil',
                        'Psicologia Social', 'Direito Constitucional', 'Estruturas de Dados',
                        'Metodologia Científica', 'Sociologia', 'Anatomia Humana'])[1 + (x.seq / 2) % 10] END,
       CASE WHEN y.devolvido AND x.seq % 5 < 2
            THEN (ARRAY['Leitura agradável, recomendo.', 'Exemplar em bom estado.',
                        'Útil para a disciplina.', 'Quero ler outros do autor.',
                        'Tradução com trechos confusos.', 'Ótimo para o TCC.'])[1 + (x.seq * 7) % 6] END,
       '10.' || (x.seq % 4) || '.' || ((x.seq / 4) % 256) || '.' || (1 + (x.seq * 31) % 254),
       md5('termo-de-responsabilidade-' || x.seq),
       CASE WHEN y.devolvido THEN x.data_emprestimo + x.duracao
            ELSE x.data_emprestimo + make_interval(secs => x.seq % 90) END,
       1 + y.renovacoes + CASE WHEN y.devolvido THEN 1 ELSE 0 END
FROM (
    SELECT r.seq,
           1 + (floor(power(r.a, 1.3) * 20000)::int * 7919 + 12345) % 20000 AS livro_id,
           1 + (floor(power(r.b, 1.3) * 10000)::int * 7907 + 4321) % 10000 AS leitor_id,
           (current_date - (1 + floor(r.c * 1095)::int))
               + make_interval(mins => 540 + floor(r.d * 660)::int) AS data_emprestimo,
           make_interval(days => 1 + floor(r.e * 27)::int, mins => floor(r.f * 600)::int) AS duracao
    FROM (SELECT g AS seq, random() AS a, random() AS b, random() AS c, random() AS d,
                 random() AS e, random() AS f
          FROM generate_series(1, 300000) AS g) AS r
) AS x
CROSS JOIN (SELECT
    ARRAY['Márcia R.', 'João P.', 'Fernanda L.', 'Ricardo S.', 'Aline M.', 'Paulo C.',
          'Beatriz T.', 'Sérgio N.', 'Cláudia F.', 'Rogério A.', 'Tânia B.', 'Wagner D.'] AS atendentes,
    ARRAY['Livro devolvido com marcações a lápis.', 'Leitor pediu renovação por telefone.',
          'Capa com pequeno desgaste na devolução.', 'Empréstimo para trabalho acadêmico.',
          'Reserva atendida na chegada do exemplar.',
          'Devolução registrada na caixa externa.'] AS observacoes
) AS a
CROSS JOIN LATERAL (
    SELECT x.data_emprestimo + x.duracao < current_date AS devolvido,
           (ARRAY['Balcão', 'Balcão', 'Balcão', 'Autoatendimento', 'Autoatendimento',
                  'Aplicativo'])[1 + (x.seq * 7) % 6] AS canal,
           CASE WHEN x.seq % 7 = 0 THEN 1 WHEN x.seq % 29 = 0 THEN 2 ELSE 0 END AS renovacoes
) AS y;

-- Livros muito procurados têm mais exemplares: cada exemplar atende uns 60 empréstimos em três anos.
UPDATE livro AS l
SET total_exemplares = ceil(p.total / 60.0),
    exemplares_disponiveis = ceil(p.total / 60.0)
FROM (SELECT livro_id, count(*) AS total FROM emprestimo GROUP BY livro_id) AS p
WHERE p.livro_id = l.id
  AND ceil(p.total / 60.0) > l.total_exemplares;

-- Um livro não pode ter mais empréstimos em aberto do que exemplares: os excedentes (os mais
-- antigos) são marcados como devolvidos um dia depois.
UPDATE emprestimo AS e
SET data_devolucao = LEAST(e.data_emprestimo + interval '1 day', current_date)
FROM (SELECT a.id
      FROM (SELECT id, livro_id,
                   row_number() OVER (PARTITION BY livro_id ORDER BY data_emprestimo DESC) AS n
            FROM emprestimo
            WHERE data_devolucao IS NULL) AS a
      JOIN livro AS l ON l.id = a.livro_id
      WHERE a.n > l.total_exemplares) AS excedente
WHERE e.id = excedente.id;

UPDATE livro AS l
SET exemplares_disponiveis = l.total_exemplares - a.abertos
FROM (SELECT livro_id, count(*) AS abertos
      FROM emprestimo
      WHERE data_devolucao IS NULL
      GROUP BY livro_id) AS a
WHERE a.livro_id = l.id;

-- Os próximos ids gerados pela aplicação continuam depois dos ids gerados aqui.
SELECT setval(pg_get_serial_sequence('categoria', 'id'), (SELECT max(id) FROM categoria));
SELECT setval(pg_get_serial_sequence('autor', 'id'), (SELECT max(id) FROM autor));
SELECT setval(pg_get_serial_sequence('livro', 'id'), (SELECT max(id) FROM livro));
SELECT setval(pg_get_serial_sequence('leitor', 'id'), (SELECT max(id) FROM leitor));
SELECT setval(pg_get_serial_sequence('emprestimo', 'id'), (SELECT max(id) FROM emprestimo));

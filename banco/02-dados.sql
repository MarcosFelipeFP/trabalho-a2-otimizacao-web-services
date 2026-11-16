-- Geração dos dados da biblioteca. A semente é fixa: toda criação do banco produz os mesmos
-- registros, com as datas contadas a partir do dia em que o banco é criado.
--
--   categoria       20
--   autor        5.000
--   livro       20.000
--   leitor      10.000
--   emprestimo 300.000   (três anos de empréstimos; os mais recentes ainda em aberto)
--
-- Alguns livros e leitores concentram mais empréstimos que outros, como numa biblioteca real.

SELECT setseed(0.2026);

-- Dígito verificador do ISBN-13 (pesos 1 e 3 alternados).
CREATE FUNCTION pg_temp.isbn13(base text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT base || ((10 - sum(substr(base, i, 1)::int * CASE WHEN i % 2 = 1 THEN 1 ELSE 3 END) % 10) % 10)::text
    FROM generate_series(1, 12) AS i
$$;

-- Nomes de pessoas, usados para autores e leitores.
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
INSERT INTO autor (id, nome, nacionalidade)
SELECT r.id,
       n.primeiros[1 + floor(r.a * array_length(n.primeiros, 1))::int] || ' ' ||
       n.sobrenomes[1 + floor(r.b * array_length(n.sobrenomes, 1))::int] || ' ' ||
       -- segundo sobrenome sempre diferente do primeiro
       n.sobrenomes[1 + (floor(r.b * array_length(n.sobrenomes, 1))::int + 1
                         + floor(r.c * (array_length(n.sobrenomes, 1) - 1))::int)
                        % array_length(n.sobrenomes, 1)],
       nac.lista[1 + floor(power(r.d, 3) * array_length(nac.lista, 1))::int]
FROM (SELECT g AS id, random() AS a, random() AS b, random() AS c, random() AS d
      FROM generate_series(1, 5000) AS g) AS r
CROSS JOIN nomes AS n
CROSS JOIN (SELECT ARRAY['Brasileira', 'Portuguesa', 'Angolana', 'Moçambicana', 'Argentina',
                         'Chilena', 'Uruguaia', 'Mexicana', 'Colombiana', 'Espanhola', 'Francesa',
                         'Italiana', 'Inglesa', 'Norte-americana', 'Japonesa'] AS lista) AS nac;

-- Livros -------------------------------------------------------------------------------------
-- Título = substantivo + adjetivo opcional + complemento. A posição k é uma permutação de
-- 0..20.399 (7919 é primo com 20.400), então os 20.000 títulos são todos diferentes.
INSERT INTO livro (id, titulo, isbn, editora, ano_publicacao, paginas, sinopse, autor_id,
                   categoria_id, total_exemplares, exemplares_disponiveis)
SELECT r.id,
       CASE WHEN r.k % 40 < 20 THEN 'O ' ELSE 'A ' END
           || t.substantivos[1 + r.k % 40]
           || CASE WHEN r.k / 1200 = 0 THEN ''
                   WHEN r.k % 40 < 20 THEN ' ' || t.adj_masc[r.k / 1200]
                   ELSE ' ' || t.adj_fem[r.k / 1200] END
           || ' ' || t.complementos[1 + (r.k / 40) % 30],
       pg_temp.isbn13('978' || lpad(((r.id::bigint * 104729) % 1000000000)::text, 9, '0')),
       t.editoras[1 + floor(r.a * array_length(t.editoras, 1))::int],
       1950 + floor((1 - power(r.b, 2)) * 76)::int,
       64 + floor(r.c * 640)::int,
       -- quatro frases diferentes, escolhidas a partir de uma posição sorteada
       t.frases[1 + (r.f) % 16] || ' ' || t.frases[1 + (r.f + 3) % 16] || ' ' ||
       t.frases[1 + (r.f + 7) % 16] || ' ' || t.frases[1 + (r.f + 11) % 16],
       1 + floor(r.d * 5000)::int,
       1 + floor(r.e * 20)::int,
       r.exemplares,
       r.exemplares
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
) AS t;

-- Leitores -----------------------------------------------------------------------------------
-- Todos se cadastraram há mais de três anos, antes do primeiro empréstimo gerado.
INSERT INTO leitor (id, nome, email, cadastrado_em)
SELECT r.id,
       p.primeiro || ' ' || p.sobrenome || ' ' || p.sobrenome2,
       lower(translate(p.primeiro || '.' || p.sobrenome,
                       'áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ', 'aaaaeeiooouucAAAAEEIOOOUUC'))
           || r.id || '@email.example',
       current_date - (1100 + floor(r.d * 1500)::int)
FROM (SELECT g AS id, random() AS a, random() AS b, random() AS c, random() AS d
      FROM generate_series(1, 10000) AS g) AS r
CROSS JOIN nomes AS n
CROSS JOIN LATERAL (
    SELECT n.primeiros[1 + floor(r.a * array_length(n.primeiros, 1))::int] AS primeiro,
           n.sobrenomes[1 + floor(r.b * array_length(n.sobrenomes, 1))::int] AS sobrenome,
           n.sobrenomes[1 + (floor(r.b * array_length(n.sobrenomes, 1))::int + 1
                             + floor(r.c * (array_length(n.sobrenomes, 1) - 1))::int)
                            % array_length(n.sobrenomes, 1)] AS sobrenome2
) AS p;

-- Empréstimos --------------------------------------------------------------------------------
-- Três anos de empréstimos, das 9h às 20h. Livros e leitores são sorteados com viés (potência
-- 1,3) e espalhados pelos ids com uma permutação, para os mais ativos não ficarem nos primeiros
-- ids. A devolução ocorre de 1 a 27 dias depois; se essa data não é anterior à meia-noite do dia
-- de criação do banco, o empréstimo fica em aberto (assim os dados não dependem da hora em que o
-- banco é criado). O prazo de devolução é de 14 dias. Os ids seguem a ordem cronológica.
INSERT INTO emprestimo (id, livro_id, leitor_id, data_emprestimo, data_prevista, data_devolucao)
SELECT row_number() OVER (ORDER BY x.data_emprestimo, x.seq),
       x.livro_id,
       x.leitor_id,
       x.data_emprestimo,
       x.data_emprestimo::date + 14,
       CASE WHEN x.data_emprestimo + x.duracao < current_date THEN x.data_emprestimo + x.duracao END
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
) AS x;

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

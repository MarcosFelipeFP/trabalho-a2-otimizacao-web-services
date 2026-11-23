# Biblioteca: otimização de Web Services com cache, consultas ao banco e testes de carga

Trabalho Prático A2 de Análise e Otimização de Sistemas (Universidade Veiga de Almeida).

| Integrante | Matrícula |
|---|---|
| Giovanni Cardoso Avallone Belo | 1230104729 |
| Luana Cristina de Azevedo Celestino | 1230206514 |
| Marcos Felipe Ferreira Pires | 1230110993 |
| Pedro Henrique Graciliano Taka | 1230119578 |

Uma API REST de biblioteca (livros, autores, categorias, leitores e empréstimos) em que a mesma
consulta existe em versões diferentes — sem e com cache; LAZY, EAGER e otimizada; sem e com
índice — para que cada técnica seja comparada por medição. Este README é o relatório técnico
pedido na seção 7.2 do enunciado; as instruções de execução estão em [Como executar](#como-executar).

## Sumário

1. [Introdução](#1-introdução)
2. [Arquitetura e tecnologias](#2-arquitetura-e-tecnologias)
3. [Implementação de cache](#3-implementação-de-cache)
4. [Otimização das consultas](#4-otimização-das-consultas)
5. [Testes de desempenho](#5-testes-de-desempenho)
6. [Discussão](#6-discussão)
7. [Conclusão](#7-conclusão)

## 1. Introdução

A aplicação é a API de uma biblioteca: catálogo de livros (com autor e categoria), leitores e
empréstimos. O enunciado não exige interface gráfica: tudo é acessado por HTTP, e a documentação
interativa em `/docs` permite chamar cada rota pelo navegador. Para a apresentação, um painel de
demonstração em `/painel` chama as mesmas rotas e mostra em destaque os números de cada resposta.

O objetivo do trabalho é aplicar três técnicas de otimização e provar o efeito de cada uma com
medições, seguindo a ideia central do enunciado: identificar o problema, implementar uma
alternativa, medir, comparar e justificar. Por isso cada operação estudada existe em mais de uma
versão, todas devolvendo exatamente o mesmo JSON, e toda resposta da API informa quantos comandos
SQL foram executados e quanto tempo se gastou no banco. O banco é um PostgreSQL no Supabase, a
cerca de 160 ms de ida e volta da API (seção 2), e por isso cada consulta economizada pesa muito
nos resultados.

| Item do enunciado | Problema estudado | Alternativas comparadas |
|---|---|---|
| 1. Cache | a ficha do livro custa três consultas e é a leitura mais frequente | sem cache; cache Redis com TTL e invalidação |
| 2. Consultas | listar empréstimos com o livro e o leitor de cada um gera o problema N+1 | LAZY, EAGER, JOIN explícito, projeção e SQL nativo |
| 2. Índices | o histórico de um leitor percorre a tabela inteira de empréstimos | sem índice; índice simples, composto e parcial |
| 3. Testes de desempenho | os ganhos se mantêm sob carga? | todas as versões acima com 10, 50, 100 e 200 usuários virtuais (Grafana k6) |

## 2. Arquitetura e tecnologias

```mermaid
flowchart LR
    navegador["curl, Postman ou /docs"] -->|HTTP| api
    subgraph local["Docker Compose, na máquina do grupo"]
        k6["Grafana k6"] -->|HTTP| api["API REST: FastAPI + uvicorn (4 processos)"]
        api -->|redis-py| cache[("Redis 8")]
    end
    api -->|"SQLAlchemy 2.1 + psycopg 3, pelo pooler do Supabase"| banco[("PostgreSQL 17 no Supabase (Ohio, EUA)")]
```

A API, o cache e o k6 rodam em contêineres (Docker Compose) na máquina do grupo; o k6 fica na
mesma rede da API. O banco é um projeto PostgreSQL no Supabase criado para este trabalho (plano
gratuito, instância Nano, região us-east-2, em Ohio), acessado pelo pooler de sessões do Supabase
(Supavisor). As credenciais ficam num arquivo `.env`, fora do Git ([`.env.exemplo`](.env.exemplo) é
o modelo).

| Camada | Tecnologia | Por que foi escolhida |
|---|---|---|
| Web Services | Python 3.14, FastAPI 0.163, uvicorn com 4 processos | API REST com validação e documentação interativa geradas a partir do código |
| Persistência | SQLAlchemy 2.1 (ORM) e psycopg 3.3 | o equivalente em Python do JPA/Hibernate que o enunciado recomenda (2.1): LAZY e EAGER declarados no relacionamento, além de JOIN explícito, busca em lote, projeções e SQL nativo |
| Banco de dados | PostgreSQL 17 no Supabase | banco gerenciado na nuvem, sem instalação; `EXPLAIN ANALYZE`, estatísticas por comando (`pg_stat_statements`) e índices parciais |
| Cache | Redis 8.10 | compartilhado pelos processos da API e com TTL próprio (seção 3.3) |
| Testes de carga | Grafana k6 2.3 | seção 5.1 |

Como cada processo Python executa código em um núcleo por vez, a API roda com 4 processos
(`--workers 4`), cada um com 3 conexões com o banco e até 40 requisições simultâneas.

### O banco no Supabase

Ter o banco a milhares de quilômetros da API muda o peso de cada decisão, e isso aparece em todos
os resultados:

- **Cada comando SQL custa uma viagem de ~160 ms.** A rota `/api/laboratorio/banco/ida-e-volta`
  executa `SELECT 1` em sequência na mesma conexão; a mediana foi de 159 ms (Rio de Janeiro →
  Ohio). As consultas deste trabalho, com os dados em memória, levam décimos de milissegundo no
  banco. Por isso o tempo de uma requisição é, quase todo, o número de consultas vezes 160 ms, e
  reduzir consultas vale mais que acelerar cada uma.
- **Leituras sem `BEGIN` e `COMMIT`.** Numa transação, o driver manda o `BEGIN` e o `COMMIT` em
  viagens separadas: duas viagens a mais por requisição. As rotas de leitura usam uma sessão em
  modo *autocommit* (`SessaoLeitura`, em [`api/app/banco.py`](api/app/banco.py)), em que só os
  comandos da requisição vão ao banco; as escritas continuam em transação.
- **15 conexões.** O pooler aceita até 15 conexões simultâneas por usuário, o padrão para a
  instância Nano. A API usa 12 (4 processos × 3), e sobram 3 para o `psql` dos experimentos. Cada
  processo atende até 40 requisições ao mesmo tempo: as que precisam do banco esperam uma conexão
  livre, e as que não precisam (acertos no cache) não entram nessa fila.
- **A instância.** PostgreSQL 17.12, `shared_buffers` de 224 MB (as tabelas da biblioteca, com
  165 MB, cabem inteiras), `random_page_cost` de 1,1 (o padrão do PostgreSQL é 4; seção 4.5) e
  `max_connections` de 60. A conexão direta do Supabase só aceita IPv6, que os contêineres do
  Docker Desktop não alcançam; por isso a API passa pelo pooler, que aceita IPv4.
- **O que não dá para medir.** A CPU e a memória do servidor do banco não são acessíveis a quem usa
  o banco. O comportamento dele foi medido pelo `pg_stat_statements`: execuções, tempo de execução,
  linhas e blocos lidos por comando.
- **A API pública do Supabase.** O Supabase também publica o schema `public` numa API REST
  automática (Data API), que qualquer um com a chave pública do projeto pode chamar. As tabelas
  têm RLS (*row level security*) ligado e nenhuma política, então essa API não lê nem altera nada.

### Entidades e volume de dados

```mermaid
erDiagram
    CATEGORIA ||--o{ LIVRO : classifica
    AUTOR ||--o{ LIVRO : escreve
    LIVRO ||--o{ EMPRESTIMO : "é emprestado em"
    LEITOR ||--o{ EMPRESTIMO : faz
```

| Tabela | Registros | Colunas | Conteúdo |
|---|---:|---:|---|
| `categoria` | 20 | 2 | gêneros (romance, ficção científica, história...) |
| `autor` | 5.000 | 9 | nome, nacionalidade, biografia, nascimento, cidade natal, prêmios |
| `livro` | 20.000 | 79 | título, ISBN, editora, ano, páginas, sinopse e exemplares; a ficha catalográfica (subtítulo, edição, idioma, tradutor, formato, dimensões, CDD, assuntos, sumário, notas, título original, série, DOI, OCLC, palavras-chave, resumo em inglês, o registro MARC 21 e uma resenha) e os dados do acervo (localização, conservação, aquisição, preço, fornecedor, tombo, conferência, reservas, avaliações) |
| `leitor` | 10.000 | 60 | nome, e-mail e o cadastro completo (carteirinha, nascimento, tipo, curso, endereço, situação, limite, multas, preferências), os documentos (CPF, RG), os contatos (telefones, contato de emergência), a conta (senha cifrada, sessão, aceite dos termos) e o programa de fidelidade |
| `emprestimo` (entidade principal) | 300.000 | 39 | livro, leitor, datas do empréstimo, prazo e devolução, canal, atendente, renovações, multa e avaliação; o protocolo, a unidade e o terminal do atendimento, o exemplar e o estado dele na retirada e na devolução, os lembretes enviados, o pagamento da multa, a finalidade, o comentário da avaliação e a assinatura do termo de responsabilidade |

**Tabelas largas, de propósito.** Uma ficha catalográfica de verdade tem dezenas de campos, e o
cadastro de um leitor também. As tabelas foram modeladas assim para que o custo de carregar
entidades inteiras apareça: a listagem de empréstimos (seção 4) mostra só o título do livro e o
nome do leitor, mas o ORM, ao carregar um `Livro`, traz as 79 colunas (cerca de 2,4 KB por linha,
com o registro MARC e a resenha) e, ao carregar um `Leitor`, as 60 (cerca de 900 bytes). É esse
volume de dados desnecessários que as consultas otimizadas evitam. A tabela de empréstimos, com 39
colunas, tem 328 bytes por linha e 94 MB: é o que uma varredura completa lê, e o que o índice da
seção 4.5 evita. As tabelas foram alargadas em 22/11/2026 (antes, 14, 47 e 28 colunas), para as
diferenças entre as estratégias ficarem mais visíveis; todas as medições deste relatório são da
versão larga.

Os dados são gerados dentro do próprio banco por [`banco/02-dados.sql`](banco/02-dados.sql), que o
`psql` executa em cerca de 75 segundos no Supabase, com semente fixa: toda instalação tem os mesmos
registros, com as datas contadas a partir do dia da criação. São três anos de empréstimos; alguns
livros e leitores concentram mais empréstimos que outros (cada leitor tem de 10 a 243, com mediana
de 28), e os empréstimos dos últimos dias ainda estão em aberto (3.722, dos quais 901 atrasados).
As cinco tabelas, com os índices, ocupam 165 MB e cabem inteiras na memória do banco
(`shared_buffers` de 224 MB).

### Web Services

| Rota | O que faz |
|---|---|
| `GET /api/livros/{id}/sem-cache` | ficha do livro, sempre montada a partir do banco (3 consultas) |
| `GET /api/livros/{id}/com-cache` | a mesma ficha, do Redis quando possível (cabeçalho `X-Cache: HIT` ou `MISS`; com o Redis fora do ar, `INDISPONIVEL`, e a ficha vem do banco, seção 3.6) |
| `PUT /api/livros/{id}` | altera dados de catálogo e invalida a ficha no cache (`X-Cache-Invalidado: sim` ou `nao`; com o Redis fora do ar, `pendente`) |
| `GET /api/livros/{id}/disponibilidade` | exemplares disponíveis, sempre do banco |
| `GET /api/emprestimos/{estratégia}?desde_id=&quantidade=` | página de empréstimos com livro e leitor, em sete estratégias de carregamento (seção 4) |
| `GET /api/emprestimos/lazy/resumo` e `/eager/resumo` | a mesma página, sem usar livro e leitor |
| `GET /api/emprestimos/atrasados` | empréstimos atrasados, dos mais antigos aos mais recentes (busca por intervalo) |
| `POST /api/emprestimos` e `POST /api/emprestimos/{id}/devolucao` | registram empréstimo e devolução, com bloqueio da linha do livro |
| `GET /api/leitores/{id}/emprestimos` | histórico de empréstimos do leitor (consulta do experimento de índices) |
| `/api/laboratorio/...` | preparam e observam os experimentos: esvaziar ou encher o cache, encurtar o TTL de uma ficha, travar o Redis por alguns segundos, alterar um título direto no banco sem avisar o cache, criar e remover índices, `EXPLAIN ANALYZE`, SQL executado por uma operação, estatísticas dos comandos no banco, ida e volta até o banco |
| `/painel/` | painel de demonstração: uma página (HTML, CSS e JavaScript, sem dependências) com a arquitetura e o volume de dados, o experimento obrigatório da 3.4 passo a passo, a queda do Redis, LAZY × EAGER, índices, comparações em volume com as métricas da 6.4 e os resultados dos testes de carga por nível; um rodapé mostra cada chamada HTTP com os cabeçalhos de medição |

**Instrumentação.** Um ouvinte de eventos do SQLAlchemy (`before_cursor_execute` e
`after_cursor_execute`) conta cada comando SQL e o tempo dele, e um middleware escreve em toda
resposta os cabeçalhos `X-Consultas-SQL` e `Server-Timing` (tempo no banco e tempo total no
servidor, em ms). As rotas `/api/laboratorio/sql/...` executam uma operação e devolvem cada comando
SQL, na ordem, com as linhas e os bytes que voltaram do banco. É daí que saem os números das
seções 3 e 4; os roteiros que os produzem estão em [`experimentos/`](experimentos).

## 3. Implementação de cache

### 3.1 O que vai para o cache

A operação escolhida é a ficha do livro: dados de catálogo, autor, categoria, total de
empréstimos e outros livros do mesmo autor. Montá-la custa três consultas (uma com JOIN entre
livro, autor e categoria, uma contagem na tabela de empréstimos e uma busca por autor), cerca de
480 ms com o banco no Supabase (seção 3.5), e ela é a leitura mais comum de um catálogo. A
decisão sobre cada parte da ficha seguiu os critérios da 3.1 do enunciado:

| Dado | Frequência de acesso | Volatilidade | Custo de buscar no banco | Se ficar desatualizado | Decisão e invalidação |
|---|---|---|---|---|---|
| Título, autor, categoria, sinopse, editora | alta: toda consulta ao catálogo | muito baixa: só muda quando a biblioteca corrige o cadastro | 2 consultas: o livro com autor e categoria (JOIN) e os outros livros do autor | um título ou sinopse antiga por alguns minutos | cache com TTL longo; a alteração pela API apaga a ficha do cache |
| Total de empréstimos e data do último | alta (faz parte da ficha) | média: muda a cada empréstimo | 1 contagem na tabela de 300.000 empréstimos | um indicador de popularidade atrasado em minutos, sem prejuízo | vai junto com a ficha, sem invalidar a cada empréstimo; o atraso fica limitado pelo TTL |
| Exemplares disponíveis | alta | alta: muda a cada empréstimo e devolução | 1 consulta pela chave do livro | o leitor vai à estante e não encontra o livro | **fora do cache**: rota própria, sempre lida do banco |

### 3.2 As duas versões

`GET /api/livros/{id}/sem-cache` monta a ficha a partir do banco em toda requisição.
`GET /api/livros/{id}/com-cache` segue a estratégia *cache-aside* ([`api/app/rotas/livros.py`](api/app/rotas/livros.py)):

```python
def ficha_com_cache(livro_id: IdDoLivro):
    chave = cache.chave_do_livro(livro_id)           # "livro:42"
    guardada = cache.ler(chave)
    if guardada is not None:                          # acerto: nenhuma consulta ao banco
        return RespostaJSON(guardada, headers={"X-Cache": "HIT"})

    corpo = para_json(_ficha_do_banco(livro_id))      # falha: três consultas
    cache.gravar(chave, corpo)                        # SET livro:42 <json> EX 600
    return RespostaJSON(corpo, headers={"X-Cache": "MISS"})
```

O cache guarda o JSON já pronto. As duas versões usam a mesma função para montar a ficha, e a
resposta só difere no cabeçalho `X-Cache`. O campo `gerada_em` mostra quando a ficha foi montada:
se ele se repete, a resposta veio do cache.

### 3.3 Tecnologia: Redis

O Redis é um armazenamento chave-valor em memória que roda como um serviço à parte. Ele foi
escolhido, e não um cache dentro da aplicação (como o `functools.lru_cache` ou o `cachetools`
do Python), porque a API roda em 4 processos. Um cache interno teria quatro cópias
independentes; uma alteração invalidaria só a cópia do processo que a recebeu, e os outros três
continuariam servindo a ficha antiga. No Redis há uma cópia só, e apagar a chave vale para todos os
processos (e para quantos servidores houver). Ele também tem TTL nativo (`SET ... EX`) e, com
`maxmemory 256mb` e `allkeys-lru`, descarta as chaves menos usadas se a memória acabar; as 20.000
fichas ocupam 25 MB (cerca de 1,3 KB cada). O custo é uma ida e volta pela rede a cada leitura e mais um
serviço para operar. Aqui o Redis roda na mesma máquina da API: a ida e volta até ele leva menos de
1 ms, contra ~160 ms até o banco no Supabase.

### 3.4 Tempo de vida e invalidação

- **TTL de 600 segundos** (`CACHE_TTL_SEGUNDOS`). Como toda alteração feita pela API já apaga a
  ficha, o TTL só limita dois atrasos: o do total de empréstimos, que nenhuma rota invalida, e o de
  alterações feitas por fora da API (uma importação, um comando SQL direto no banco). Dez minutos
  são aceitáveis para dados de catálogo e mantêm a ficha no cache durante uma sessão inteira de
  navegação. O efeito de outros valores de TTL foi medido na seção 5.
- **Invalidação**: `PUT /api/livros/{id}` altera o livro e, depois do *commit*, apaga a chave.
  Apagar antes do *commit* abriria uma janela em que uma leitura simultânea guardaria de novo a
  versão antiga.

```python
    with Sessao.begin() as sessao:                    # transação: commit no fim do bloco
        livro = sessao.get(Livro, livro_id)
        for nome, valor in campos.items():
            setattr(livro, nome, valor)
        livro.atualizado_em = datetime.now()

    invalidou = cache.invalidar(cache.chave_do_livro(livro_id))   # DEL livro:42
```

**Experimento obrigatório** ([`experimentos/cache.py`](experimentos/cache.py)), com o TTL
reduzido para 20 s para a espera do passo 5 caber na demonstração:

| Passo | Operação | X-Cache | Consultas SQL | Tempo no servidor | Título devolvido | Ficha gerada às |
|---|---|---|---:|---:|---|---|
| 1 | GET com cache, cache vazio | MISS | 3 | 445,65 ms | A Biblioteca Eterna dos Esquecidos | 17:26:11.168 |
| 2 | GET com cache de novo | HIT | 0 | 0,50 ms | A Biblioteca Eterna dos Esquecidos | 17:26:11.168 |
| 3 | `PUT /api/livros/42` com título novo | – | 5 | 1.053,45 ms | (resposta: `X-Cache-Invalidado: sim`) | – |
| 4a | GET com cache depois do PUT | MISS | 3 | 447,72 ms | ... dos Esquecidos (edição revista) | 17:26:12.675 |
| 4b | GET com cache de novo | HIT | 0 | 0,55 ms | ... dos Esquecidos (edição revista) | 17:26:12.675 |
| 5a | `UPDATE` direto no banco, por fora da API | – | – | – | – | – |
| 5b | GET com cache | HIT | 0 | 0,71 ms | ... (edição revista), **o título antigo** | 17:26:12.675 |
| 5c | GET com cache depois de o TTL acabar | MISS | 3 | 466,02 ms | ... (edição revista) [alterado direto no banco] | 17:26:42.245 |

Horários no relógio do contêiner da API (UTC). O PUT leva cerca de 1 s porque faz sete viagens ao
banco: `BEGIN`, a leitura e a alteração do livro, `COMMIT` e as três consultas da ficha atualizada
que ele devolve.

O passo 2 mostra o reaproveitamento (mesma `gerada_em`, nenhuma consulta). Os passos 3 e 4 mostram
a invalidação: a primeira leitura depois da alteração já traz o título novo. O passo 5 mostra o
limite dessa estratégia: uma alteração feita por fora da API não avisa o cache, e a ficha antiga
continua sendo servida (5b) até expirar (5c). **Riscos**: durante esse intervalo o usuário vê um
dado que não existe mais; se o dado em cache fosse usado para uma decisão (por exemplo, permitir um
empréstimo), o erro seria grave. Por isso a disponibilidade ficou fora do cache e o registro de
empréstimo confere o estoque no banco, com a linha do livro bloqueada (`SELECT ... FOR UPDATE`).
Resta ainda uma janela rara de corrida: uma leitura que buscou a versão antiga antes do *commit*
pode gravá-la no cache logo depois da invalidação; o TTL também limita esse caso.

O painel (`/painel/`, seção Cache) repete os cinco passos com a API no ar e o TTL padrão, marcando
cada um quando a resposta mostra o comportamento esperado. Para o passo 5, duas rotas de
laboratório substituem o `psql` e a recriação da API: `PUT /api/laboratorio/banco/livros/{id}/titulo`
faz o `UPDATE` por fora da API, sem avisar o cache, e
`PUT /api/laboratorio/cache/livros/{id}/ttl?segundos=15` encurta o tempo de vida só daquela ficha
(`EXPIRE` no Redis), para a expiração caber na demonstração.

### 3.5 Análise de desempenho do cache

Uma requisição por vez, 300 livros sorteados ([`experimentos/resultados/cache.md`](experimentos/resultados/cache.md)):

| Situação | Consultas SQL por requisição | Tempo no servidor (mediana) | p95 | Tempo total no cliente (mediana) |
|---|---:|---:|---:|---:|
| sem cache | 3 | 478,12 ms | 490,06 ms | 478,86 ms |
| com cache, falha (ficha ainda não guardada) | 3 | 479,95 ms | 496,01 ms | 480,65 ms |
| com cache, acerto | 0 | 0,35 ms | 0,41 ms | 0,80 ms |

O acerto é mais de mil vezes mais rápido no servidor (0,35 ms contra 478 ms) e não consulta o
banco: somem as três viagens até Ohio. A falha custa praticamente o mesmo que não ter cache: ela
paga as três consultas e mais uma leitura e uma gravação no Redis, que está na mesma máquina e leva
menos de 1 ms, abaixo da variação da rede até o banco (a falha chegou a sair 8 ms mais rápida, o
que é ruído).

Sob carga (seção 5.3, cenário 1), com 50 VUs: sem cache, 25,7 req/s e 2.000 ms de latência média;
com o cache quente, 6.765 req/s e 7,3 ms; com o cache frio, esvaziado logo antes da medição,
30,2 req/s e 1.675 ms, com 14% de acertos. O efeito do TTL foi medido à parte, com o cache
começando vazio (seção 5.3, "Extra: efeito do TTL"): com TTL de 5 s, a taxa de acerto ficou em
torno de 6% e a vazão em 27 req/s; com 120 ou 600 s, a taxa chegou a 26% no fim do minuto
medido, e a vazão, a 32 req/s.

**Em quais situações o cache apresentou maior benefício?** Quando a mesma ficha é lida muitas vezes
antes de mudar ou expirar, e mais ainda sob carga. Sem cache, cada ficha prende uma conexão com o
banco durante três viagens (~465 ms), e a fila por conexões cresce com o número de usuários: a
latência média foi de 0,59 s com 10 VUs para 8,5 s com 200. No acerto, o banco nem é consultado, e
a API sustentou de 5.800 a 6.800 req/s com latência média abaixo de 31 ms em todos os níveis. O benefício
também depende de quantas leituras se repetem: num catálogo, poucos livros concentram a maior parte
das consultas, e são eles que o cache passa a atender primeiro.

**Como a volatilidade dos dados influenciou a escolha do TTL?** Os dados de catálogo quase nunca
mudam, e toda alteração feita pela API já apaga a ficha; o TTL não precisa ser curto para que uma
alteração apareça. Ele só limita o atraso do que muda sem invalidação: o total de empréstimos, que
muda a cada empréstimo, e as alterações feitas por fora da API. Por isso 600 s: o total de
empréstimos pode atrasar até dez minutos, o que não prejudica ninguém. A disponibilidade, que muda a
cada empréstimo e decide se o leitor encontra o livro na estante, não tolera atraso nenhum e ficou
fora do cache. O experimento do TTL mostra o custo de errar para o lado curto: com 5 s, a taxa de
acerto ficou em torno de 6%, e o cache quase não aliviou o banco; com 30 s, ela parou de subir
(entre 15% e 19%) assim que as fichas começaram a expirar; com 120 ou 600 s, continuou subindo até
o fim. Um TTL curto paga o custo de um dado volátil sem que o dado seja volátil.

**Quais são os riscos de utilizar informações desatualizadas?** Mostrar ao leitor um título, uma
sinopse ou um total de empréstimos que já mudaram (passo 5b do experimento da seção 3.4); tomar
uma decisão com base num dado antigo, como liberar o empréstimo de um livro sem exemplar
disponível; e, com vários processos ou servidores, cada um servir uma versão diferente, se o cache
ficasse dentro de cada processo (o motivo do Redis, seção 3.3). As defesas adotadas: invalidar a
ficha no `PUT`, depois do *commit*; o TTL como limite para o que escapa da invalidação; e os dados
que decidem alguma coisa (a disponibilidade) sempre lidos do banco, com o empréstimo conferindo o
estoque com a linha do livro bloqueada.

**O cache sempre melhorou o desempenho?** Não. Na falha, a requisição paga as três consultas e
ainda uma leitura e uma gravação no Redis: 480 ms contra 478 ms sem cache, uma requisição por vez
(a diferença é ruído). Com o cache frio, a taxa de acerto em 30 s ficou entre 9% e 14%, e o ganho
foi nenhum com 10 VUs (18 req/s nas duas versões) e de 20% com 50 VUs; os limites do k6 estouraram
do mesmo jeito. Depois de uma alteração, a leitura seguinte volta a pagar as três consultas (passo
4a da seção 3.4: 466 ms). Com um TTL curto, a ficha expira antes de ser pedida de novo (com 5 s,
cerca de 6% de acertos e 27 req/s, perto dos 25 req/s de sem cache). E, mesmo acertando sempre, o
cache não eliminou o limite, só o mudou de lugar: com o cache quente, o gargalo passou a ser a CPU
da API. O cache melhora o desempenho na medida da taxa de acerto, que depende da repetição das
leituras, do TTL e das invalidações.

### 3.6 Extra: e se o Redis cair?

O cache é um atalho: a ficha está no banco, e o Redis guarda só uma cópia. Na primeira versão da
API, porém, uma falha do Redis derrubava as rotas que o usam. Com o contêiner do Redis parado
(`docker compose stop cache`), antes e depois desta seção:

| Requisição | Antes | Agora |
|---|---|---|
| `GET /api/livros/42/com-cache` | 500, depois de 3,3 a 4,4 s | 200 com `X-Cache: INDISPONIVEL`: a ficha vem do banco (3 consultas) |
| `PUT /api/livros/42` | 500, depois de 3,3 s, **com a alteração já gravada no banco** | 200 com `X-Cache-Invalidado: pendente` |
| `GET /api/laboratorio/estado` (usado pelo painel) | 500 | 200, com `"redis": null` |
| as outras rotas de laboratório do cache | 500 | 503, com a explicação |

O PUT era o pior caso: quem chamava recebia um erro de uma alteração que tinha dado certo, e podia
repeti-la. Três mecanismos, em [`api/app/cache.py`](api/app/cache.py), fazem a API seguir sem o
Redis:

- **Tempo limite de 0,5 s** (`CACHE_TEMPO_LIMITE_S`) para conectar e para cada leitura no Redis,
  sem novas tentativas. Uma leitura no Redis leva menos de 1 ms; meio segundo só se esgota se ele
  parou de responder. Quando o tempo acaba ou a conexão falha, `ler`, `gravar` e `invalidar`
  levantam `CacheIndisponivel`, e a rota busca a ficha no banco:

  ```python
  try:
      guardada = cache.ler(chave)
  except cache.CacheIndisponivel:                   # Redis fora do ar: a ficha vem do banco
      return RespostaJSON(_ficha_do_banco(livro_id), headers={"X-Cache": "INDISPONIVEL"})
  ```

- **Uma vigia no lugar das novas tentativas.** Depois da primeira falha, o processo da API para de
  tentar o Redis nas requisições, que vão direto ao banco, e uma thread em segundo plano testa o
  Redis a cada segundo (`PING`). Isso importa porque nem toda falha é rápida: com o contêiner
  parado, o nome `cache` deixa de existir, e o DNS do Docker leva uns 3 s para responder que ele
  não existe, tempo que o limite de 0,5 s não cobre. Sem a vigia, uma requisição a cada poucos
  segundos pagaria esses 3 s.
- **Invalidação pendente.** Se o PUT não consegue apagar a ficha, a chave fica numa lista do
  processo. Quando o Redis volta, a vigia apaga as chaves pendentes e só então devolve o cache às
  requisições. Sem isso, um Redis que volta com os dados de antes (travado, e não reiniciado)
  serviria a ficha antiga até o TTL acabar.

[`experimentos/falha_do_cache.py`](experimentos/falha_do_cache.py) tira o Redis do ar de dois
jeitos: parado (`docker compose stop cache`) e travado (`docker compose pause cache`, que congela o
processo com as fichas na memória e deixa as conexões abertas, sem resposta). Os tempos abaixo
foram medidos com o banco no Supabase, como o resto do relatório: uma ficha montada no banco leva
~480 ms (seção 3.5). Os tempos de detecção da falha (o DNS e o tempo limite) não dependem do
banco. Todas as linhas estão em
[`falha_do_cache.md`](experimentos/resultados/falha_do_cache.md):

| Parte | Situação | X-Cache | Consultas SQL | Tempo no servidor | Título devolvido |
|---|---|---|---:|---:|---|
| A | Redis parado: 1ª leitura com cache | INDISPONIVEL | 3 | 8.453 ms | o original |
| A | Redis parado: as 9 leituras seguintes (mediana) | INDISPONIVEL | 3 | 479,0 ms | o original |
| A | sem cache, para comparar (mediana de 10) | – | 3 | 485,6 ms | o original |
| A | PUT com o Redis parado | `X-Cache-Invalidado: pendente` | 5 | 1.188 ms | o novo (A) |
| A | Redis de volta, 5,4 s depois do `start` | MISS, e depois HIT | 3 e 0 | 480,5 e 0,8 ms | o novo (A) |
| B | Redis travado: 1ª leitura com cache | INDISPONIVEL | 3 | 979,4 ms | o novo (A) |
| B | PUT com o Redis travado | `X-Cache-Invalidado: pendente` | 5 | 1.120 ms | o novo (B) |
| B | as 9 leituras seguintes, em 8 s (mediana) | INDISPONIVEL | 3 | 478,8 ms | o novo (B) |
| B | Redis de volta, 1,5 s depois do `unpause` | **MISS**, e depois HIT | 3 e 0 | 479,3 e 0,5 ms | **o novo (B)** |

A primeira leitura de cada processo espera a falha aparecer: cerca de 8 s com o contêiner parado (a
busca do nome `cache`, que só falha depois de esgotar as tentativas no DNS; numa rodada anterior, em
outra rede, foram 3,3 s) e 0,5 s com o Redis travado (o tempo limite); os ~480 ms restantes são a
ficha montada no banco. As seguintes custam o mesmo que a versão sem cache. Na parte A, a vigia levou
5,4 s para perceber a volta do Redis, porque cada tentativa dela, com o contêiner parado, também
espera a busca no DNS falhar; nesse intervalo, as leituras continuaram vindo do banco, sem erro. A
parte B é a prova da invalidação pendente: o Redis volta com a ficha antiga na memória, e a primeira
leitura é MISS com o título novo, e não HIT com o antigo.

Sob carga, com o Redis parado (k6, `VERSAO=redis-fora`; banco local, para que a vazão não fique presa
aos ~26 req/s do Supabase; três execuções de cada versão, alternadas, nos quatro níveis da matriz;
[`testes-carga/resultados/2026-11-22_19h49_redis-fora/`](testes-carga/resultados/2026-11-22_19h49_redis-fora)):

| VUs | Sem cache | Com cache, Redis parado | Diferença na vazão | Erros com o Redis parado |
|---:|---:|---:|---:|---:|
| 10 | 1.472 req/s, média de 6,7 ms | 1.372 req/s, média de 7,2 ms | −6,8% | 0% |
| 50 | 1.439 req/s, média de 35,1 ms | 1.469 req/s, média de 34,0 ms | +2,1% | 0% |
| 100 | 1.435 req/s, média de 69,7 ms | 1.405 req/s, média de 71,3 ms | −2,1% | 0% |
| 200 | 1.364 req/s, média de 148,0 ms | 1.378 req/s, média de 145,8 ms | +1,0% | 0% |

Nenhuma requisição falhou, e a vazão com o Redis parado ficou entre 7% abaixo e 2% acima da versão
sem cache: diferenças do tamanho da variação entre as repetições de uma mesma versão (até ±15%).
Cada processo registra no log um aviso quando percebe a falha e outro quando o Redis volta
(`cache.py`). A primeira execução deste teste, com as tabelas ainda estreitas, três níveis de carga
e uma execução de cada versão, está em
[`testes-carga/resultados/2026-11-22_redis-fora/`](testes-carga/resultados/2026-11-22_redis-fora), com
o mesmo resultado: nenhum erro e a vazão perto da versão sem cache.

**Limites.**

- Sem o Redis, o banco recebe toda a carga. Com o Supabase, a ficha volta aos ~26 req/s de sem
  cache (seção 5.3): a queda para o banco mantém a API no ar, não o desempenho.
- A volta do Redis é um cache frio, porque ele não grava nada em disco, e as primeiras leituras são
  falhas (o cenário do cache frio da seção 5.3).
- Cada processo descobre a falha sozinho, na primeira requisição que tenta o Redis depois da queda:
  ela e as que estiverem esperando o Redis no mesmo processo, naquele momento, pagam a detecção
  (cerca de 8 s ou 0,5 s); as seguintes, não.
- A lista de invalidações pendentes fica na memória do processo que recebeu o PUT. Um processo que
  não percebeu a queda pode servir a ficha antiga por até ~1 s depois que o Redis volta, até a vigia
  do outro apagá-la. Se a API reiniciar com o Redis fora do ar, a lista se perde, e só o TTL limita
  a ficha antiga.
- O painel trava o Redis com `CLIENT PAUSE` (`POST /api/laboratorio/cache/pausar`), porque não tem
  acesso ao Docker. Nos testes, essa pausa às vezes terminou antes do tempo pedido (7,5 s de 10 s);
  por isso o roteiro congela o contêiner, que fica parado exatamente o tempo que o roteiro decide.

## 4. Otimização das consultas

### 4.1 e 4.2 LAZY e EAGER

O relacionamento estudado é Empréstimo → Livro e Empréstimo → Leitor: a listagem devolve uma
página de empréstimos com o título do livro e o nome do leitor de cada um. No SQLAlchemy, a
estratégia é declarada no relacionamento, como o `FetchType` do JPA
([`api/app/modelos.py`](api/app/modelos.py)). A tabela é mapeada duas vezes para as duas versões
existirem lado a lado:

```python
class Emprestimo(Base):                     # LAZY: busca o livro só quando o código o acessa
    __tablename__ = "emprestimo"
    ...
    livro: Mapped[Livro] = relationship(lazy="select")
    leitor: Mapped[Leitor] = relationship(lazy="select")


class EmprestimoEager(Base):                # EAGER: a mesma tabela, com o livro e o leitor
    __table__ = Emprestimo.__table__        # trazidos na mesma consulta, com JOIN
    livro: Mapped[Livro] = relationship(lazy="joined", viewonly=True)
    leitor: Mapped[Leitor] = relationship(lazy="joined", viewonly=True)
```

A rota é a mesma nas duas versões; só muda a classe consultada. O SQL abaixo foi registrado pela
rota de laboratório para uma página de 3 empréstimos (todos os comandos estão em
[`experimentos/resultados/sql/`](experimentos/resultados/sql)):

```sql
-- LAZY: 7 comandos. A página vem primeiro; cada livro e cada leitor é buscado no momento em que
-- a resposta é montada (e.livro.titulo, e.leitor.nome), intercalados, um empréstimo por vez.
-- Cada um traz a entidade inteira: as 39 colunas do empréstimo, as 79 do livro, as 60 do leitor.
SELECT emprestimo.id, emprestimo.livro_id, emprestimo.leitor_id, ... FROM emprestimo
WHERE emprestimo.id >= 150000 ORDER BY emprestimo.id LIMIT 3;
SELECT livro.id, livro.titulo, livro.isbn, ..., livro.sumario, livro.notas, ... FROM livro WHERE livro.id = 13400;
SELECT leitor.id, leitor.nome, leitor.email, ..., leitor.observacoes, ... FROM leitor WHERE leitor.id = 8581;
SELECT ... FROM livro WHERE livro.id = 3487;
SELECT ... FROM leitor WHERE leitor.id = 7635;
SELECT ... FROM livro WHERE livro.id = 10307;
SELECT ... FROM leitor WHERE leitor.id = 53;

-- EAGER: 1 comando, 178 colunas (todas as de empréstimo, livro e leitor) para usar 8 delas
SELECT emprestimo.id, ..., livro_1.id AS id_1, livro_1.titulo, ..., livro_1.sumario, ...,
       leitor_1.id AS id_2, leitor_1.nome, ..., leitor_1.atualizado_em AS atualizado_em_1
FROM emprestimo
LEFT OUTER JOIN livro AS livro_1 ON livro_1.id = emprestimo.livro_id
LEFT OUTER JOIN leitor AS leitor_1 ON leitor_1.id = emprestimo.leitor_id
WHERE emprestimo.id >= 150000 ORDER BY emprestimo.id LIMIT 3;
```

O LAZY tem o problema N+1: 1 consulta para a página e mais 2 por empréstimo (menos os livros e
leitores repetidos, que o SQLAlchemy reaproveita da sessão). No SQLAlchemy, o EAGER declarado com
`lazy="joined"` resolveu tudo numa consulta, mas **EAGER não garante uma consulta só** (4.2 do
enunciado): a mesma intenção, "carregar antes", com outra forma de busca, deu resultados bem
diferentes:

- `selectinload` (EAGER em consultas separadas): 1 consulta para a página e 1 para todos os livros
  (`WHERE id IN (...)`), mais 1 para os leitores. O SQLAlchemy divide a lista do `IN` em lotes de
  500 ids; até 500 empréstimos por página, são sempre 3 consultas.
- `immediateload` (EAGER que busca cada objeto logo após carregar a página): o mesmo N+1 do LAZY,
  só que antes de a resposta ser montada. É o comportamento do EAGER do Hibernate numa consulta
  JPQL sem `JOIN FETCH`.

### 4.3 Comparação com diferentes quantidades de registros

[`experimentos/carregamento.py`](experimentos/carregamento.py) mediu cada estratégia com páginas de
10 a 500 empréstimos, uma requisição por vez. Cada tempo é a mediana de 15 requisições; nas
estratégias com N+1, que chegam a levar dois minutos e meio por requisição, de 1 a 3:

| Consultas SQL por requisição | 10 | 50 | 100 | 200 | 500 |
|---|---:|---:|---:|---:|---:|
| LAZY | 21 | 101 | 200 | 398 | 983 |
| EAGER (`lazy="joined"`) | 1 | 1 | 1 | 1 | 1 |
| EAGER com `selectinload` | 3 | 3 | 3 | 3 | 3 |
| EAGER com `immediateload` | 21 | 101 | 200 | 398 | 983 |
| JOIN FETCH (`joinedload`) | 1 | 1 | 1 | 1 | 1 |
| otimizada (projeção) | 1 | 1 | 1 | 1 | 1 |
| SQL nativo | 1 | 1 | 1 | 1 | 1 |

| Tempo no servidor, em ms (mediana) | 10 | 50 | 100 | 200 | 500 |
|---|---:|---:|---:|---:|---:|
| LAZY | 3.303,6 | 15.863,7 | 31.916,8 | 63.505,1 | 156.557,7 |
| EAGER (`lazy="joined"`) | 164,0 | 170,9 | 178,0 | 197,6 | 244,6 |
| EAGER com `selectinload` | 477,7 | 491,1 | 510,2 | 543,5 | 619,1 |
| EAGER com `immediateload` | 3.302,3 | 15.889,1 | 31.372,9 | 63.248,4 | 155.688,2 |
| JOIN FETCH (`joinedload`) | 162,0 | 170,3 | 190,8 | 218,9 | 256,4 |
| otimizada (projeção) | 158,8 | 159,2 | 159,5 | 163,6 | 168,5 |
| SQL nativo | 157,0 | 158,1 | 159,7 | 162,8 | 165,6 |

| Volume lido do banco, em KB | 10 | 50 | 100 | 200 | 500 |
|---|---:|---:|---:|---:|---:|
| LAZY, `selectinload` e `immediateload` (entidades inteiras) | 30,8 | 153,9 | 305,6 | 610,8 | 1.515,7 |
| EAGER e JOIN FETCH (entidades inteiras, num JOIN) | 30,8 | 153,9 | 307,5 | 614,3 | 1.538,3 |
| otimizada e SQL nativo (só as 8 colunas da resposta) | 1,1 | 5,4 | 10,8 | 21,6 | 54,1 |
| resposta da API, em JSON (igual em todas) | 2,3 | 11,4 | 22,8 | 45,6 | 114,2 |

O N+1 faz o número de consultas e o tempo crescerem na proporção do tamanho da página: com 500
empréstimos, o LAZY fez 983 consultas e levou 157 s, mais de 600 vezes o EAGER (245 ms). Executar
cada consulta custa décimos de milissegundo ao banco, mas cada uma paga a viagem até ele: o tempo
no banco medido pela API foi de 160 ms por consulta, quase todo rede. Com o banco remoto, o N+1
deixa de ser um custo e vira um defeito: uma página de só 10 empréstimos já leva 3,4 s. As
estratégias de uma consulta, ao contrário, quase não sentem o tamanho da página: de 10 para 500
empréstimos, o EAGER passou de 164 para 245 ms, e a projeção, de 159 para 169 ms.

**Volume de informações e dados desnecessários.** Para a mesma resposta de 114 KB com 500
empréstimos, o banco devolveu 1.538 KB ao EAGER (500 linhas de 178 colunas, com a sinopse, o sumário, o registro
MARC e a resenha de cada livro), 1.516 KB ao LAZY (1.482 linhas, em 983 consultas) e 54 KB à versão
otimizada, 28 vezes menos que o EAGER. Com páginas grandes, esse volume já aparece no tempo: com 500
empréstimos, o EAGER levou 245 ms e a projeção, 169 ms (45% a mais); com 10, a diferença foi de 5 ms. O
custo do EAGER aparece também quando a resposta não usa os relacionamentos: nas versões "resumo",
que devolvem só os dados do empréstimo, o mapeamento EAGER continua fazendo o JOIN e trazendo todas
as colunas de livro e leitor, cerca de 10 vezes mais dados que o LAZY:

| Versão "resumo" (sem livro e leitor) | Consultas | Lido do banco | Tempo no servidor |
|---|---:|---:|---:|
| LAZY, 20 empréstimos | 1 | 6,1 KB | 160,43 ms |
| EAGER, 20 empréstimos | 1 | 61,5 KB | 166,36 ms |
| LAZY, 500 empréstimos | 1 | 151,4 KB | 181,24 ms |
| EAGER, 500 empréstimos | 1 | 1.538,3 KB | 259,78 ms |

Com 500 empréstimos, os dados que a resposta não usa custaram 79 ms a mais no servidor (260 contra
181 ms).

**Quando usar cada um.** LAZY é o padrão mais seguro: não carrega o que não é usado e funciona bem
para objetos isolados ou relacionamentos raramente acessados; o perigo é percorrer uma lista
acessando o relacionamento, que gera o N+1. EAGER compensa quando o relacionamento é usado
praticamente sempre que a entidade é lida, mas, declarado no mapeamento, ele vale para todas as
consultas, inclusive as que não precisam dos dados (as versões "resumo"). A escolha melhor é
manter o mapeamento LAZY e pedir o carregamento antecipado em cada consulta que precisa dele
(`joinedload` ou `selectinload`), como o `JOIN FETCH` do JPA. Para coleções (um-para-muitos), o
`selectinload` evita multiplicar as linhas da consulta principal, que o JOIN causaria.

### 4.4 Otimização das consultas

Partindo do LAZY original, foram implementadas três alternativas
([`api/app/rotas/emprestimos.py`](api/app/rotas/emprestimos.py)):

```python
# JOIN FETCH: o mapeamento continua LAZY, mas esta consulta pede livro e leitor com JOIN
consulta = _pagina(Emprestimo, desde_id, quantidade).options(
    joinedload(Emprestimo.livro), joinedload(Emprestimo.leitor))

# otimizada: projeção (DTO), uma consulta com JOIN que traz só as 8 colunas da resposta
consulta = (
    select(Emprestimo.id, Emprestimo.data_emprestimo, Emprestimo.data_prevista,
           Emprestimo.data_devolucao, Livro.id.label("livro_id"), Livro.titulo,
           Leitor.id.label("leitor_id"), Leitor.nome)
    .join(Livro, Livro.id == Emprestimo.livro_id)
    .join(Leitor, Leitor.id == Emprestimo.leitor_id)
    .where(Emprestimo.id >= desde_id).order_by(Emprestimo.id).limit(quantidade))

# nativa: a mesma consulta, escrita à mão
SQL_NATIVO = text("""
    SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao,
           l.id AS livro_id, l.titulo, r.id AS leitor_id, r.nome
    FROM emprestimo e
    JOIN livro l ON l.id = e.livro_id
    JOIN leitor r ON r.id = e.leitor_id
    WHERE e.id >= :desde_id ORDER BY e.id LIMIT :quantidade""")
```

O `JOIN FETCH` gera o mesmo SQL do EAGER (o mesmo JOIN, com as 178 colunas) e teve praticamente o
mesmo tempo (212,5 contra 205,7 ms com 500 empréstimos), sem impor o JOIN às outras consultas. A
versão otimizada foi a mais rápida das que usam o ORM: com 500 empréstimos, 169 ms contra 245 ms
do EAGER e 157 s do LAZY. Ela lê 28 vezes menos dados (54 KB contra 1.538 KB) e não cria
entidades; com o banco longe, quase todo o resto é a própria viagem. Sob carga, a comparação está
na seção 5.

**O SQL nativo trouxe benefício real?** Com o banco no Supabase, não. Ele executa a mesma consulta
da versão otimizada (as duas leram 54 KB), e a diferença de tempo entre as duas ficou abaixo de
3 ms em todos os tamanhos de página, perto da variação entre medições: o trabalho que o SQLAlchemy
faz a mais para montar a consulta e ler o resultado some perto da viagem de 160 ms. Sob carga
(seção 5.3), o SQL nativo usou um pouco menos de CPU na API (17% contra 20% de um núcleo com
50 VUs), e as diferenças de vazão e de latência entre os dois ficaram dentro da variação entre as
repetições. Com o banco local (seção 5.4), em que a CPU da API passou a ser o limite, essa economia
virou vazão: 2.470 contra 2.057 req/s com 50 VUs (20% mais), com 1,1 ms de CPU por requisição
contra 1,5 ms. O ganho grande (cerca de 930 vezes com 500 empréstimos, de 157 s para 0,17 s) veio
de eliminar o N+1 e de buscar só as colunas usadas, e o ORM faz as duas coisas. Em troca, o SQL
nativo cobra na manutenção: é texto que o ORM não confere (um nome de coluna errado só aparece
quando a rota roda), não acompanha uma mudança no mapeamento, exige converter as linhas à mão e
depende do dialeto do banco (`LIMIT` e as conversões de tipo mudam entre PostgreSQL, SQL Server e
Oracle). Faz sentido usá-lo em consultas que o ORM não expressa bem (funções de janela, CTEs
recursivas, dicas específicas do banco) ou numa rota muito usada em que a CPU da API seja o limite
e a medição mostre o ganho, não como regra.

### 4.5 Índices (seção 5 do enunciado)

A consulta escolhida é o histórico de empréstimos de um leitor, no mesmo formato do exemplo do
enunciado (filtro por chave estrangeira, JOIN e ordenação):

```sql
SELECT e.id, e.data_emprestimo, e.data_prevista, e.data_devolucao, l.id, l.titulo
FROM emprestimo e JOIN livro l ON l.id = e.livro_id
WHERE e.leitor_id = 150
ORDER BY e.data_emprestimo DESC;
```

No estado inicial, `emprestimo(leitor_id)` não tem índice (o PostgreSQL não cria índice para chave
estrangeira). O índice proposto é `CREATE INDEX idx_emprestimo_leitor_data ON emprestimo (leitor_id, data_emprestimo DESC)`.
[`experimentos/indices.py`](experimentos/indices.py) comparou cinco situações, para o leitor 150
(58 empréstimos) e para o leitor com mais empréstimos (4322, com 243). Os planos completos estão
em [`experimentos/resultados/planos/`](experimentos/resultados/planos):

| Situação | Leitor | Operações na tabela `emprestimo` | Sort | Linhas descartadas | Execução no banco |
|---|---|---|---|---:|---:|
| 1. sem índice | 150 | Parallel Seq Scan | sim | 299.942 | 35,221 ms |
| 1. sem índice | 4322 | Parallel Seq Scan | sim | 299.756 | 51,852 ms |
| 2. índice só em `leitor_id` | 150 | Index Scan | sim | 0 | 0,381 ms |
| 2. índice só em `leitor_id` | 4322 | Index Scan | sim | 0 | 1,231 ms |
| 3. índice proposto | 150 | Index Scan, já na ordem | não | 0 | 0,347 ms |
| 3. índice proposto | 4322 | Index Scan, já na ordem | não | 0 | 1,127 ms |
| 4. índice proposto, `random_page_cost` = 4 | 150 | Bitmap Index Scan + Bitmap Heap Scan | sim | 0 | 0,402 ms |
| 4. índice proposto, `random_page_cost` = 4 | 4322 | Bitmap Index Scan + Bitmap Heap Scan | sim | 0 | 1,511 ms |
| 5. índice proposto, `LIMIT 10` | 150 | Index Scan, já na ordem | não | 0 | 0,113 ms |
| 5. índice proposto, `LIMIT 10` | 4322 | Index Scan, já na ordem | não | 0 | 0,115 ms |

Execução no banco: mediana de 15 `EXPLAIN ANALYZE`, com o `random_page_cost` de 1,1 do Supabase,
exceto na situação 4. Trechos dos planos (`EXPLAIN (ANALYZE, BUFFERS)`):

```
-- 1. sem índice: lê a tabela inteira (12.004 páginas) e descarta quase tudo
Gather Merge  (cost=15253.38..15255.45 rows=18 width=60) (actual time=34.549..41.494 rows=58 loops=1)
  Workers Planned: 1
  Workers Launched: 1
  ->  Sort  (cost=14253.37..14253.41 rows=18 width=60) (actual time=26.922..26.925 rows=29 loops=2)
        Sort Key: emprestimo.data_emprestimo DESC
        ->  Nested Loop  (cost=0.29..14252.99 rows=18 width=60) (actual time=1.096..26.868 rows=29 loops=2)
              ->  Parallel Seq Scan on emprestimo  (cost=0.00..14209.88 rows=18 width=32) (actual time=1.071..26.598 rows=29 loops=2)
                    Filter: (leitor_id = 150)
                    Rows Removed by Filter: 149971
                    Buffers: shared hit=12004
              ->  Index Scan using livro_pkey on livro  (cost=0.29..2.40 rows=1 width=32) (actual time=0.007..0.007 rows=1 loops=58)
                    Index Cond: (id = emprestimo.livro_id)
Execution Time: 41.553 ms

-- 3. índice proposto: só as 58 linhas do leitor, já na ordem pedida; o Sort sumiu
Nested Loop  (cost=0.71..106.90 rows=30 width=60) (actual time=0.022..0.325 rows=58 loops=1)
  ->  Index Scan using idx_emprestimo_leitor_data on emprestimo  (cost=0.42..35.05 rows=30 width=32) (actual time=0.014..0.080 rows=58 loops=1)
        Index Cond: (leitor_id = 150)
        Buffers: shared hit=61
  ->  Index Scan using livro_pkey on livro  (cost=0.29..2.40 rows=1 width=32) (actual time=0.004..0.004 rows=1 loops=58)
        Index Cond: (id = emprestimo.livro_id)
Execution Time: 0.362 ms

-- 4. o mesmo índice com random_page_cost = 4: só acha as linhas (bitmap) e o Sort volta
Sort  (cost=358.42..358.49 rows=30 width=60) (actual time=0.373..0.378 rows=58 loops=1)
  Sort Key: emprestimo.data_emprestimo DESC
  ->  Nested Loop  (cost=4.94..357.68 rows=30 width=60) (actual time=0.037..0.350 rows=58 loops=1)
        ->  Bitmap Heap Scan on emprestimo  (cost=4.66..120.53 rows=30 width=32) (actual time=0.028..0.117 rows=58 loops=1)
              Recheck Cond: (leitor_id = 150)
              Heap Blocks: exact=58
              ->  Bitmap Index Scan on idx_emprestimo_leitor_data  (cost=0.00..4.65 rows=30 width=0) (actual time=0.014..0.015 rows=58 loops=1)
                    Index Cond: (leitor_id = 150)
        ->  Index Scan using livro_pkey on livro  (cost=0.29..7.90 rows=1 width=32) (actual time=0.003..0.003 rows=1 loops=58)
              Index Cond: (id = emprestimo.livro_id)
Execution Time: 0.418 ms
```

Na API, o histórico do leitor 150 passou de 227,2 ms para 158,2 ms no servidor. Também foi medida
a busca por intervalo (os 50 empréstimos atrasados mais antigos: `data_devolucao IS NULL AND
data_prevista < hoje ORDER BY data_prevista`): sem índice, 33,6 ms com Parallel Seq Scan; com o
índice parcial `ON emprestimo (data_prevista) WHERE data_devolucao IS NULL`, de apenas 48 KB,
0,82 ms.

**O índice foi efetivamente utilizado?** Sim: a varredura completa (Seq Scan) deu lugar ao
`Index Scan` em `idx_emprestimo_leitor_data`, e as 299.942 linhas descartadas pelo filtro caíram
para zero. O índice composto foi usado por inteiro: o banco percorre as entradas do leitor já na
ordem de `data_emprestimo DESC`, e o `Sort` sumiu do plano. O índice só em `leitor_id` acha as
mesmas linhas, mas precisa ordená-las depois. O plano também mostra outro índice que já existia,
`livro_pkey`, usado no JOIN com `livro` em todas as situações (como o enunciado alerta na 5.2).

**Houve redução no tempo de execução?** Sim, de 35,2 ms para 0,35 ms no banco, cerca de 100 vezes.
Na API, o histórico passou de 227 para 158 ms: os 69 ms economizados no banco já são 30% do tempo
da requisição, mas a viagem de ~160 ms até ele continua sendo a maior parte. O ganho grande aparece
quando o banco fica ocupado, sob carga (seção 5): sem índice, cada requisição ocupa o banco por
35 ms; com índice, por 0,3 ms.

**Quais fatores influenciaram o resultado?**

- *Seletividade*: o leitor 150 tem 58 dos 300.000 empréstimos (0,02%). Com tão poucas linhas, o
  índice vence com folga; para o leitor com 243 empréstimos, o tempo com índice subiu para 1,10 ms
  (cresce com as linhas do leitor), enquanto a varredura completa custa quase o mesmo para todos.
- *Modelo de custos do planejador*: o `random_page_cost` diz quanto custa ler uma página fora de
  ordem. O padrão do PostgreSQL é 4, pensado para disco magnético; o Supabase usa 1,1, valor
  indicado para SSD. Com 1,1, percorrer o índice na ordem pedida sai barato, e o `Sort` some. Com 4
  (situação 4), o mesmo índice só serve para achar as linhas, que são lidas na ordem física da
  tabela e ordenadas depois. O plano depende da configuração do banco, não só do índice.
- *LIMIT*: pedindo só os 10 mais recentes, o banco lê as 10 primeiras entradas do leitor e para:
  0,11 ms, seja qual for o leitor.
- *Correlação física*: os empréstimos de um leitor estão espalhados pela tabela, uma página para
  cada (58 linhas em 58 páginas, `Heap Blocks: exact=58` no plano 4), porque a tabela está em
  ordem de data e não de leitor.

**Quais podem ser os custos de manter índices adicionais?** Espaço e escrita. O índice proposto
ocupa 9,0 MB, quatro vezes o índice só em `leitor_id` (2,2 MB), que se beneficia da deduplicação
de chaves repetidas do PostgreSQL; a tabela inteira tem 94 MB (as 12.004 páginas que a varredura
completa lê). E todo `INSERT` precisa atualizar cada índice: inserir 20.000 empréstimos (numa
transação desfeita no fim; tempo de execução no banco, mediana de 5) levou 42,5 µs por linha sem
os índices do experimento, 61,2 µs com o índice proposto (+44%) e 84,6 µs com os três (+99%).
Também há mais trabalho de `VACUUM` e mais páginas disputando a memória do banco.

| Índices extras em `emprestimo` | Tamanho dos índices | Inserir 20.000 empréstimos | Por linha |
|---|---:|---:|---:|
| nenhum (só chave primária e `livro_id`) | 8,9 MB | 851 ms | 42,5 µs |
| `(leitor_id, data_emprestimo DESC)` | 17,9 MB | 1.224 ms | 61,2 µs |
| os três do experimento | 20,1 MB | 1.693 ms | 84,6 µs |

**Criar índices em todas as colunas consultadas seria uma boa estratégia?** Não. Cada índice só
ajuda as consultas que filtram ou ordenam pelas colunas dele, na ordem certa e com seletividade
suficiente; em colunas pouco seletivas (como `data_devolucao IS NULL` sem ser parcial, ou uma
categoria entre 20) o planejador prefere a varredura completa e o índice só ocupa espaço. E todos
eles encarecem cada escrita, justamente na tabela que mais recebe escritas (a de empréstimos). O
caminho é indexar as consultas que importam, conferir com `EXPLAIN ANALYZE` se o índice é usado e
preferir índices que sirvam a mais de uma consulta, ou parciais quando só uma fração das linhas
interessa, como o dos empréstimos em aberto.

## 5. Testes de desempenho

### 5.1 Ferramenta: Grafana k6

O k6 é uma ferramenta de código aberto da Grafana Labs para testes de carga. Os testes são scripts
em JavaScript ([`testes-carga/k6/`](testes-carga/k6)), versionados junto com o código, e o próprio
k6 calcula as métricas pedidas (latência média, p95, p99, vazão e taxa de erros), confere limites
de aceitação (*thresholds*) e tem um painel web com gráficos ao vivo, que também exporta um
relatório HTML. Ele foi escolhido por isso e por rodar pela linha de comando, num contêiner, sem
interface gráfica: a matriz inteira de testes roda sem intervenção.

Cada script define, com os *scenarios* do k6, os níveis de carga em sequência. Em cada nível há
10 s de aquecimento, descartados, e 30 s de medição. As métricas de cada nível saem separadas
graças às *tags* `fase` e `carga`, e os limites são conferidos nível a nível
([`testes-carga/k6/comum.js`](testes-carga/k6/comum.js)):

```js
scenarios[`aquecimento_${vus}vus`] = { executor: 'constant-vus', vus, duration: '10s',
  startTime: `${t}s`, tags: { fase: 'aquecimento', carga } };
scenarios[`medicao_${vus}vus`] = { executor: 'constant-vus', vus, duration: '30s',
  startTime: `${t + 10}s`, tags: { fase: 'medicao', carga } };

thresholds[`http_req_duration{fase:medicao,carga:${vus}}`] = ['p(95)<1000', 'p(99)<2000'];
thresholds[`http_req_failed{fase:medicao,carga:${vus}}`] = ['rate<0.01'];
```

Os limites (p95 abaixo de 1 s, p99 abaixo de 2 s e menos de 1% de erros) levam em conta a
distância do banco: sem carga nenhuma, uma ficha montada no banco já leva cerca de 0,48 s (três
consultas de ~160 ms). Eles marcam o nível de carga a partir do qual a fila pesa mais que o
trabalho. O k6 espera até 60 s por resposta; depois disso, a requisição conta como erro.

Além das métricas do k6, cada requisição registra três métricas próprias, lidas dos cabeçalhos da
API: consultas SQL por requisição, tempo no banco e acerto do cache.

### 5.2 Cenários e cargas

| Cenário | Script | Versões comparadas | Requisição |
|---|---|---|---|
| 1. Cache | `cache.js` | sem cache; cache frio (esvaziado logo antes de cada medição); cache quente (as 20.000 fichas guardadas antes do teste, de uma vez, por `POST /api/laboratorio/cache/encher`) | ficha de um livro sorteado entre 20.000, com popularidade: 1% dos livros recebe 22% das requisições, e 10% recebe 46% |
| 2. Persistência | `persistencia.js` | LAZY, EAGER, otimizada e SQL nativo | página de 20 empréstimos a partir de um id sorteado; o EAGER traz 178 colunas por linha, a otimizada 8 |
| 3. Índices | `indice.js` | sem índice; com o índice proposto | histórico de um leitor sorteado entre 10.000 |
| Extra: banco local | os três | as versões dos cenários 1, 2 e 3 | as mesmas, com o banco num contêiner na mesma máquina (seção 5.4) |
| Extra: TTL | `cache.js` | TTL de 5, 30, 120 e 600 s, com o cache começando vazio | ficha, 50 VUs, 60 s |

**Cargas**: 10, 50, 100 e 200 usuários virtuais (VUs) simultâneos. Cada VU manda a próxima
requisição assim que recebe a resposta; o número de VUs é a concorrência, não a vazão, que é
medida (6.3 do enunciado).

**Cuidados na execução** (6.5), todos automáticos em [`testes-carga/executar.py`](testes-carga/executar.py):

- todas as versões de um cenário recebem as mesmas cargas e durações, no mesmo ambiente;
- o estado inicial é preparado pelo próprio script do k6, no `setup()`: o cache é esvaziado ou
  enchido e o índice é criado ou removido, pelas rotas de laboratório;
- antes de tudo, as tabelas são carregadas na memória do banco (`pg_prewarm`) e todos os
  endpoints são aquecidos; depois, cada nível tem 10 s de aquecimento descartados;
- antes de cada execução, o contêiner da API é recriado. Sob carga alta, o LAZY deixa requisições
  na fila da API depois que o k6 desiste delas, e a execução seguinte começaria com essa fila;
- cada execução registra o volume de dados, os índices existentes e a configuração da API, e o
  início da matriz registra a ida e volta até o banco (`ambiente.json`);
- três repetições, com a ordem das versões alternada a cada repetição;
- o k6 roda num contêiner na mesma rede da API: medido antes, o encaminhamento de portas do Docker
  Desktop para o Windows acrescentava cerca de 1 ms por requisição e limitava a vazão (4.900 req/s
  contra 6.217 req/s no mesmo endpoint com cache);
- a CPU dos contêineres locais (API, Redis e k6) e a memória da API e do Redis são lidas a cada
  segundo dos contadores do cgroup, mais exatos que o `docker stats`. O banco no Supabase não
  mostra a CPU; no lugar dela, um `psql` conectado lê a cada segundo o tempo de execução acumulado
  no `pg_stat_statements`, e os comandos de cada execução (a diferença entre o antes e o depois)
  ficam guardados;
- o banco é um projeto do Supabase criado só para este trabalho, e a carga respeita os limites do
  plano gratuito (a 6.5 do enunciado pede ambientes próprios ou autorizados);
- dois contêineres de outro projeto (`petmotion`) ficaram ligados na máquina durante as medições;
  eles aparecem no ambiente registrado, e a CPU que usaram está em `execucoes.csv` (coluna
  `cpu_outros_pct`).

### 5.3 Resultados

A matriz completa tem 39 execuções do k6: 27 dos três cenários (9 versões, 3 repetições, cada
execução com os quatro níveis de carga) e 12 do experimento do TTL. Ela rodou de uma vez em
22/11/2026, das 15h45 às 17h54, com as tabelas e os volumes da seção 2. Cada número abaixo é a
média das três repetições. Tudo o que foi medido está em
[`testes-carga/resultados/2026-11-22_15h45/`](testes-carga/resultados/2026-11-22_15h45): o resumo gerado
pelo `analisar.py` ([`resumo.md`](testes-carga/resultados/2026-11-22_15h45/resumo.md)), uma linha por
nível de carga de cada execução (`execucoes.csv`), os relatórios HTML do painel do k6 (`html/`), os
comandos SQL de cada execução segundo o `pg_stat_statements` (`banco/`) e o ambiente
(`ambiente.json`). A matriz anterior, com as tabelas estreitas (89 colunas no EAGER e 4.265 páginas
na tabela de empréstimos), está em
[`testes-carga/resultados/2026-11-20_21h56/`](testes-carga/resultados/2026-11-20_21h56); ela aparece
abaixo só para comparar.

**Comparação das versões com 50 VUs**, a carga "média" da 6.3, no formato da tabela da 6.6:

| Cenário | Versão | Latência média | p95 | p99 | Vazão | Erros | Consultas SQL por requisição |
|---|---|---:|---:|---:|---:|---:|---:|
| 1. Cache | sem cache | 2.000 ms | 2.392 ms | 3.802 ms | 25,7 req/s | 0% | 3 |
| 1. Cache | cache frio | 1.675 ms | 3.887 ms | 4.125 ms | 30,2 req/s | 0% | 2,6 |
| 1. Cache | cache quente | 7,3 ms | 15,1 ms | 20,8 ms | 6.765 req/s | 0% | 0 |
| 2. Persistência | LAZY | 21.045 ms¹ | 29.285 ms¹ | 29.848 ms¹ | 0,8 req/s | 0% | 41 |
| 2. Persistência | EAGER | 703 ms | 1.100 ms | 1.418 ms | 72,1 req/s | 0% | 1 |
| 2. Persistência | otimizada (projeção) | 684 ms | 843 ms | 1.230 ms | 74,1 req/s | 0% | 1 |
| 2. Persistência | SQL nativo | 693 ms | 882 ms | 1.177 ms | 73,4 req/s | 0% | 1 |
| 3. Índices | sem índice | 1.414 ms | 2.326 ms | 3.776 ms | 36,1 req/s | 0% | 1 |
| 3. Índices | com índice | 720 ms | 1.343 ms | 1.683 ms | 71,1 req/s | 0% | 1 |

¹ Só as requisições que terminaram dentro da janela de medição de 30 s; as outras foram
interrompidas pelo k6 no fim do nível.

Nenhuma requisição respondida falhou: a taxa de erros foi 0% em todos os níveis de todas as
execuções. Sob saturação, a API não recusa requisições, ela as enfileira, e o custo aparece na
latência.

**O teto de vazão.** Quase todos os resultados se explicam por uma conta. A API tem 12 conexões
com o banco, e cada consulta prende uma conexão durante uma viagem de ~155 ms. Uma requisição
que faz *n* consultas prende a conexão por *n* × 155 ms, e a vazão máxima é 12 ÷ (*n* × 0,155 s):
cerca de 77 req/s com uma consulta, 26 req/s com as três da ficha e menos de 2 req/s com as 41 do
LAZY. Acima desse teto, mais usuários só aumentam a fila: a vazão para de subir e a latência cresce
na proporção da carga (pela lei de Little, latência média ≈ VUs ÷ vazão; com 200 VUs e 73 req/s,
2,7 s, como medido na versão otimizada).

#### Cenário 1: cache

| VUs | Versão | Vazão (req/s) | Média (ms) | p95 (ms) | p99 (ms) | Erros | Acertos no cache | SQL por req. | CPU da API | Banco executando | Variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem cache | 17 | 594 | 778 | 1.257 | 0,00% | – | 3,0 | 11% | 14% | ±18,0% |
| 10 | cache frio | 16 | 655 | 1.142 | 1.408 | 0,00% | 9% | 2,7 | 11% | 16% | ±24,7% |
| 10 | cache quente | 5.773 | 1,63 | 3,44 | 5,31 | 0,00% | 100% | 0,0 | 296% | 0% | ±11,3% |
| 50 | sem cache | 26 | 2.000 | 2.392 | 3.802 | 0,00% | – | 3,0 | 15% | 18% | ±1,9% |
| 50 | cache frio | 30 | 1.675 | 3.887 | 4.125 | 0,00% | 14% | 2,6 | 14% | 43% | ±4,0% |
| 50 | cache quente | 6.765 | 7,28 | 15,1 | 20,8 | 0,00% | 100% | 0,0 | 316% | 0% | ±8,9% |
| 100 | sem cache | 24 | 4.065 | 9.091 | 12.640 | 0,00% | – | 3,0 | 14% | 19% | ±2,3% |
| 100 | cache frio | 30 | 3.181 | 8.514 | 9.428 | 0,00% | 13% | 2,6 | 15% | 16% | ±2,8% |
| 100 | cache quente | 6.532 | 15,3 | 33,6 | 48,4 | 0,00% | 100% | 0,0 | 319% | 0% | ±14,0% |
| 200 | sem cache | 21 | 8.477 | 18.110 | 22.388 | 0,00% | – | 3,0 | 14% | 15% | ±2,1% |
| 200 | cache frio | 28 | 6.720 | 11.895 | 15.887 | 0,00% | 14% | 2,6 | 15% | 14% | ±4,1% |
| 200 | cache quente | 6.579 | 30,3 | 51,8 | 77,7 | 0,00% | 100% | 0,0 | 323% | 0% | ±8,1% |

CPU da API em % de um núcleo (400% = os quatro processos ocupados o tempo todo). Banco executando:
soma do tempo de execução das consultas da API no banco (`pg_stat_statements`) dividida pela
duração da medição; 100% equivale a uma consulta executando o tempo todo, e 400%, a quatro ao
mesmo tempo. Variação: maior distância entre a vazão de uma repetição e a média.

![Cenário 1: ficha do livro sem e com cache](testes-carga/resultados/2026-11-22_15h45/graficos/cache.svg)

- **Sem cache**, a vazão ficou entre 21 e 26 req/s a partir de 50 VUs, o teto das três consultas
  da ficha (cada requisição passou ~465 ms no banco). Dali em diante só a fila cresceu: a latência
  média foi de 0,59 s (10 VUs) a 8,5 s (200 VUs), e o p99 chegou a 22 s.
- **Cache quente**: de 5.800 a 6.800 req/s, sem nenhuma consulta ao banco. Com 50 VUs, a vazão foi
  263 vezes a de sem cache, e a latência média, 7,3 ms contra 2.000 ms. O limite passou a ser a CPU
  da API, de 300% a 320% dos 400% que os quatro processos podem usar; o k6, na mesma máquina, usou
  mais ~145%. A latência ainda cresce com a carga (de 1,6 para 30 ms), agora na fila da CPU.
- **Cache frio**, esvaziado antes de cada nível: em 30 s só os livros mais procurados se repetem,
  e a taxa de acerto ficou entre 9% e 14%. O ganho foi pequeno: nenhum com 10 VUs (16 contra
  17 req/s de sem cache, dentro da variação) e 18% de vazão com 50 VUs (30,2 contra 25,7 req/s).
  Os limites do k6 estouraram em todos os níveis do cache frio e a partir de 50 VUs sem cache; com
  o cache quente, todos os níveis ficaram dentro deles.

#### Cenário 2: estratégias de persistência

| VUs | Versão | Vazão (req/s) | Média (ms) | p95 (ms) | p99 (ms) | Erros | SQL por req. | CPU da API | Banco executando | Variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | LAZY | 0,8 | 11.356 | 22.834 | 25.301 | 0,00% | 41,0 | 9% | 5% | ±10,0% |
| 10 | EAGER | 38 | 268 | 423 | 546 | 0,00% | 1,0 | 22% | 22% | ±23,4% |
| 10 | otimizada | 51 | 198 | 289 | 370 | 0,00% | 1,0 | 15% | 22% | ±7,7% |
| 10 | SQL nativo | 45 | 230 | 385 | 503 | 0,00% | 1,0 | 12% | 75% | ±25,3% |
| 50 | LAZY | 0,8 | 21.045 | 29.285 | 29.848 | 0,00% | 41,0 | 11% | 5% | ±60,9% |
| 50 | EAGER | 72 | 703 | 1.100 | 1.418 | 0,00% | 1,0 | 40% | 21% | ±0,1% |
| 50 | otimizada | 74 | 684 | 843 | 1.230 | 0,00% | 1,0 | 20% | 15% | ±7,7% |
| 50 | SQL nativo | 73 | 693 | 882 | 1.177 | 0,00% | 1,0 | 17% | 61% | ±10,0% |
| 100 | LAZY | 0,1 | 17.209 | 22.605 | 23.032 | 0,00% | 41,0 | 12% | 5% | ±66,7% |
| 100 | EAGER | 69 | 1.476 | 3.159 | 5.743 | 0,00% | 1,0 | 37% | 47% | ±5,1% |
| 100 | otimizada | 75 | 1.354 | 3.316 | 5.097 | 0,00% | 1,0 | 20% | 14% | ±5,4% |
| 100 | SQL nativo | 67 | 1.531 | 4.296 | 7.083 | 0,00% | 1,0 | 16% | 150% | ±13,1% |
| 200 | LAZY | 0,0 | 25.976 | 28.562 | 28.707 | 0,00% | 41,0 | 12% | 4% | – |
| 200 | EAGER | 62 | 3.241 | 7.273 | 9.659 | 0,00% | 1,0 | 37% | 114% | ±14,9% |
| 200 | otimizada | 75 | 2.688 | 6.188 | 8.508 | 0,00% | 1,0 | 21% | 13% | ±2,7% |
| 200 | SQL nativo | 66 | 3.183 | 7.474 | 10.569 | 0,00% | 1,0 | 17% | 151% | ±25,1% |

**LAZY com 200 VUs**: em duas das três repetições, nenhuma requisição terminou dentro da janela
de medição; as latências dessa linha são as da repetição restante.

![Cenário 2: página de 20 empréstimos com livro e leitor](testes-carga/resultados/2026-11-22_15h45/graficos/persistencia.svg)

- **LAZY**: 41 consultas por requisição (1 para a página e 2 por empréstimo), cada uma com sua
  viagem até o banco, ou seja, 6,4 s no banco por requisição. Com 10 VUs, 0,8 req/s e 11,4 s de
  latência média; com 50 e 100 VUs, a latência chegou perto do tamanho da janela (p95 de 23 a 29 s)
  e a vazão caiu até 0,1 req/s; com 200 VUs, em duas das três repetições nenhuma requisição
  terminou dentro da janela. Cada requisição dura mais que o aquecimento, e as que o k6 abandona no
  fim de um nível continuam ocupando conexões na API durante o seguinte: o LAZY nunca chega a um
  regime estável, e os números dele mostram o colapso, não uma capacidade.
- **EAGER, otimizada e SQL nativo** fazem uma consulta só e chegaram perto do mesmo teto, de 72 a
  74 req/s com 50 VUs. A diferença está no que cada uma traz: o EAGER lê as 178 colunas do
  empréstimo, do livro e do leitor (63 KB por página); a projeção e o SQL nativo, só as 8 da
  resposta (2,2 KB). Com as tabelas largas, essa diferença chegou ao usuário:
  - com 10 VUs, o EAGER levou 268 ms em média, contra 198 ms da projeção (35% a mais);
  - com 50 VUs, a vazão foi quase a mesma (72 contra 74 req/s), mas o p95 do EAGER foi de 1.100 ms,
    contra 843 ms: ele estourou o limite de 1 s já nesse nível, e a projeção, só com 100 VUs;
  - com 200 VUs, o EAGER atendeu 62 req/s, contra 75 da projeção (21% a menos), com latência
    média de 3,2 s contra 2,7 s. Pela conta do teto, cada requisição do EAGER prendeu a conexão
    ~190 ms, contra ~160 ms: o tempo de trazer e transformar em objetos quase 30 vezes mais dados.
    Parte da diferença nesse nível vem da repetição 3, em que o banco ficou lento (ver as
    observações abaixo); na repetição 2, sem lentidão, foram 70 contra 76 req/s.

  Na matriz anterior, com as tabelas estreitas, as três versões tinham ficado empatadas em todos
  os níveis: alargar as tabelas tornou visível o custo de carregar entidades inteiras.
- **O custo das 178 colunas** também aparece nos recursos. Com a mesma vazão, o EAGER ocupou o
  dobro da CPU da API (de 37% a 40% de um núcleo, contra 20% da projeção e 16% a 17% do SQL
  nativo), porque transforma cada linha em objetos com todas as colunas, e mais memória (444 contra
  399 MB com 200 VUs). No banco, cada requisição do EAGER leu 152 blocos, contra 128: os 24 a mais
  são as colunas longas do livro (sinopse, sumário, registro MARC e resenha), que o PostgreSQL
  guarda fora da linha (TOAST) e só lê quando a consulta as pede.
- **SQL nativo e projeção** fazem a mesma consulta (o mesmo JOIN, as mesmas 8 colunas, os mesmos
  blocos) e empataram nos níveis em que a instância não ficou lenta. As médias do SQL nativo ficaram
  um pouco piores por causa de três níveis lentos (ver as observações), e não por causa da consulta.

#### Cenário 3: índices

| VUs | Versão | Vazão (req/s) | Média (ms) | p95 (ms) | p99 (ms) | Erros | SQL por req. | CPU da API | Banco executando | Variação |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | sem índice | 32 | 319 | 447 | 615 | 0,00% | 1,0 | 11% | 351% | ±11,3% |
| 10 | com índice | 48 | 212 | 351 | 567 | 0,00% | 1,0 | 15% | 87% | ±18,4% |
| 50 | sem índice | 36 | 1.414 | 2.326 | 3.776 | 0,00% | 1,0 | 12% | 620% | ±1,9% |
| 50 | com índice | 71 | 720 | 1.343 | 1.683 | 0,00% | 1,0 | 20% | 47% | ±10,9% |
| 100 | sem índice | 37 | 2.741 | 5.320 | 9.473 | 0,00% | 1,0 | 13% | 603% | ±3,9% |
| 100 | com índice | 75 | 1.360 | 3.565 | 5.366 | 0,00% | 1,0 | 20% | 56% | ±2,4% |
| 200 | sem índice | 34 | 5.575 | 12.155 | 16.465 | 0,00% | 1,0 | 12% | 596% | ±2,5% |
| 200 | com índice | 72 | 2.813 | 6.377 | 8.659 | 0,00% | 1,0 | 19% | 76% | ±3,3% |

![Cenário 3: histórico de empréstimos de um leitor, sem e com índice](testes-carga/resultados/2026-11-22_15h45/graficos/indice.svg)

- **Sem índice**, o gargalo foi o próprio banco. Cada requisição percorreu a tabela de
  empréstimos (mais de 12.000 blocos por consulta, a tabela inteira, contra ~123 com o índice), e o
  banco executando passou de 590% a partir de 50 VUs: em média, seis varreduras ao mesmo tempo.
  Disputando a CPU da instância, cada varredura levou de 150 a 180 ms no banco, cerca de cinco vezes
  os 35 ms medidos com uma consulta por vez (seção 4.5), e a vazão parou em ~36 req/s.
- **Com o índice**, a vazão subiu até o teto das conexões. Com 50 VUs: praticamente o dobro da
  vazão (71,1 contra 36,1 req/s), latência média 49% menor (720 contra 1.414 ms) e p95 42% menor
  (1.343 contra 2.326 ms); com 100 e 200 VUs, também o dobro. Com uma requisição por vez, o ganho na
  API tinha sido de 69 ms (seção 4.5): o índice vale mais justamente quando o banco está ocupado.
  Na matriz anterior, com a tabela de empréstimos quase três vezes menor, o ganho com 50 VUs tinha
  sido de 58%: quanto maior a tabela, mais cara a varredura que o índice evita.
- Com o índice, o banco executando variou de 22% a 122%, conforme o nível e a repetição, e o tempo
  de execução por requisição, de 3,5 a 31 ms, lendo sempre os mesmos ~123 blocos. A variação vem
  das lentidões da instância (ver as observações abaixo), e não da consulta.

#### Memória

A memória dos contêineres foi lida junto com a CPU: a maior leitura de cada janela de medição
(`memory.current` do cgroup), em MB, média das repetições. A memória do servidor do banco não é
acessível no Supabase.

| Cenário | Versão | API, 10 VUs | API, 50 VUs | API, 100 VUs | API, 200 VUs | Redis (todos os níveis) |
|---|---|---:|---:|---:|---:|---:|
| 1. Cache | sem cache | 380 | 388 | 396 | 401 | 7 a 8 |
| 1. Cache | cache frio | 382 | 387 | 402 | 411 | 7 a 9 |
| 1. Cache | cache quente | 548 | 520 | 521 | 530 | 31 a 32 |
| 2. Persistência | LAZY | 378 | 395 | 404 | 422 | 15 a 16 |
| 2. Persistência | EAGER | 387 | 415 | 436 | 444 | 9 a 17 |
| 2. Persistência | otimizada | 376 | 383 | 391 | 399 | 8 a 10 |
| 2. Persistência | SQL nativo | 373 | 382 | 388 | 395 | 8 a 10 |
| 3. Índices | sem índice | 373 | 383 | 395 | 397 | 7 a 8 |
| 3. Índices | com índice | 378 | 386 | 397 | 403 | 7 a 9 |

- A memória não foi limite em nenhum cenário. Fora do cache quente, a API ficou entre 373 e
  444 MB, menos de 8% dos 5,8 GB da máquina virtual do Docker, e cresceu no máximo 15% de 10 para
  200 VUs, com mais requisições em andamento ao mesmo tempo. O EAGER foi o que mais cresceu (de 387
  para 444 MB, contra 373 a 395 MB do SQL nativo): cada requisição em andamento mantém na memória
  objetos com as 178 colunas.
- O Redis passou de ~7 MB, vazio, para 31 MB com as 20.000 fichas: a diferença, ~24 MB, são as
  fichas (seção 3.3), o custo de memória do cache.
- No cache quente, a API ocupou de 125 a 170 MB a mais que sem cache, desde o nível de 10 VUs, e a
  memória não cresceu com a carga. O acréscimo vem do preparo, não das requisições: para encher o
  cache, um dos processos monta as 20.000 fichas de uma vez (`POST /api/laboratorio/cache/encher`)
  e continua com essa memória. Medido à parte, com a API recém-recriada, esse processo passou de
  107 para 302 MB, e o contêiner, de 348 para 544 MB.

#### Extra: efeito do TTL

O cache começa vazio e a carga é de 50 VUs por 60 s, com a API recriada com cada TTL
(`CACHE_TTL_SEGUNDOS`); três repetições de cada.

| TTL | Vazão (req/s) | Média (ms) | p95 (ms) | Acertos no cache (60 s) | Acertos nos últimos 20 s | Variação |
|---:|---:|---:|---:|---:|---:|---:|
| 5 s | 27 | 1.855 | 2.420 | 6% | 5% | ±1,2% |
| 30 s | 31 | 1.662 | 2.393 | 15% | 16% | ±3,9% |
| 120 s | 32 | 1.569 | 2.753 | 19% | 26% | ±2,7% |
| 600 s | 32 | 1.587 | 2.382 | 19% | 26% | ±5,3% |

![Taxa de acerto do cache ao longo do tempo, por TTL](testes-carga/resultados/2026-11-22_15h45/graficos/ttl.svg)

- Com 5 s, a ficha quase sempre expira antes de ser pedida de novo; só os livros mais procurados
  se repetem tão rápido. A taxa de acerto ficou em torno de 6% do começo ao fim, e a vazão
  (27 req/s), perto da de sem cache (26 req/s com 50 VUs, no cenário 1).
- Com 30 s, a taxa sobe enquanto o cache se enche e para de subir a partir dos 30 s, quando as
  primeiras fichas começam a expirar: fica entre 16% e 20%.
- Com 120 e 600 s, nenhuma ficha expira dentro do minuto medido, e as duas curvas andam juntas,
  subindo até o fim (26% nos últimos 20 s, nas duas). Um TTL maior que o intervalo entre duas leituras
  da mesma ficha não muda nada; abaixo disso, cada redução derruba a taxa de acerto.
- Mesmo no melhor caso, a vazão subiu pouco, de 27 para 32 req/s: com 20.000 livros e ~30 leituras
  por segundo, a maior parte das leituras de um minuto é de livros ainda não guardados. O TTL
  define o teto da taxa de acerto; quem a enche é a repetição das leituras.

**Observações sobre a execução.**

- A matriz rodou de uma vez, sem interrupções. A ida e volta até o banco, medida no início, teve
  mediana de 152,7 ms (`ambiente.json`). Nenhuma execução precisou ser refeita, e nenhum nível ficou
  sem requisições, fora o LAZY com 200 VUs, que não termina nenhuma dentro da janela.
- A instância do Supabase (Nano, com CPU compartilhada) ficou mais lenta em níveis isolados de
  algumas execuções. O tempo de execução no banco por requisição, que fica entre 1,5 e 3 ms nas
  versões de uma consulta do cenário 2, subiu para 15 a 86 ms no SQL nativo (repetição 1 com 100 e
  200 VUs, repetição 2 com 50 e 100 VUs, repetição 3 com 10 VUs) e no EAGER (repetição 3 com 100 e
  200 VUs), lendo as mesmas linhas e os mesmos blocos. Nesses níveis a vazão caiu (até 49 req/s,
  no SQL nativo com 200 VUs), e as médias das duas versões carregam essas quedas. A coluna
  `banco_execucao_pct` de `execucoes.csv` mostra cada caso.
- Os contêineres do outro projeto (seção 5.2) ficaram abaixo de 8% de um núcleo em todos os níveis
  (coluna `cpu_outros_pct`).

### 5.4 Cenário extra: o banco na mesma máquina

Com o banco no Supabase, a viagem de ~155 ms até ele explica quase todos os resultados da seção 5.3.
Para ver o que muda sem ela, os cenários 1, 2 e 3 foram repetidos com o banco num contêiner local
(perfil `banco-local` do Compose: PostgreSQL 17, 256 MB de `shared_buffers`), com o mesmo código, os
mesmos dados e a mesma matriz (27 execuções: 3 repetições, 4 níveis de carga, 10 s de aquecimento e
30 s de medição). A ida e volta da API até o banco caiu de 152,7 ms para 0,23 ms (mediana). O banco
local divide as 6 CPUs da máquina virtual do Docker com a API, o Redis e o k6, e a CPU dele também
foi medida. Os resultados estão em
[`testes-carga/resultados/2026-11-22_18h55/`](testes-carga/resultados/2026-11-22_18h55), no mesmo
formato da seção 5.3.

**Comparação com 50 VUs.** CPU da API por requisição: o tempo de CPU dos quatro processos dividido
pelas requisições atendidas. CPU do banco: em % de um núcleo, como a da API.

| Cenário | Versão | Vazão no Supabase | Vazão local | Local ÷ Supabase | Latência média local | p95 local | CPU da API por requisição | CPU do banco |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1. Cache | sem cache | 25,7 req/s | 1.452 req/s | 56× | 34,4 ms | 72,7 ms | 2,5 ms | 50% |
| 1. Cache | cache frio | 30,2 req/s | 3.613 req/s | 120× | 13,8 ms | 41,1 ms | 0,9 ms | 24% |
| 1. Cache | cache quente | 6.765 req/s | 6.450 req/s | 0,95× | 7,7 ms | 16,4 ms | 0,5 ms | 2% |
| 2. Persistência | LAZY | 0,8 req/s | 174 req/s | 217× | 291 ms | 465 ms | 21,9 ms | 67% |
| 2. Persistência | EAGER | 72,1 req/s | 1.101 req/s | 15× | 45,5 ms | 138 ms | 2,8 ms | 131% |
| 2. Persistência | otimizada (projeção) | 74,1 req/s | 2.057 req/s | 28× | 24,3 ms | 60,3 ms | 1,5 ms | 118% |
| 2. Persistência | SQL nativo | 73,4 req/s | 2.470 req/s | 34× | 20,5 ms | 48,9 ms | 1,1 ms | 139% |
| 3. Índices | sem índice | 36,1 req/s | 123 req/s | 3,4× | 416 ms | 1.040 ms | 2,9 ms | 531% |
| 3. Índices | com índice | 71,1 req/s | 2.488 req/s | 35× | 20,1 ms | 54,4 ms | 1,3 ms | 50% |

Erros: 0% em todos os níveis de todas as execuções, como no Supabase.

- **A viagem sumiu, e o gargalo passou a ser a CPU.** Sem cache, a ficha foi de 25,7 para 1.452
  req/s com 50 VUs, e a CPU da API chegou a 359% dos 400% possíveis (quatro processos, cada um usa
  no máximo um núcleo): cada ficha custa ~2,5 ms de CPU na API (as três consultas pelo ORM e a
  resposta em JSON), e é esse custo, e não mais a espera pelo banco, que limita a vazão. Nas versões
  rápidas dos cenários 2 e 3, a API ficou entre 278% e 335%, dividindo as 6 CPUs da máquina virtual
  com o banco e o k6: somados, os contêineres usaram de 457% a 493%.
- **O cache ganhou bem menos.** O cache quente ficou em 6.450 req/s, perto dos 6.765 do Supabase
  (nos dois, sem consultas, o limite é a CPU), mas, como a ficha sem cache ficou muito mais barata,
  o ganho caiu de 263 vezes para 4,4 vezes. O cache frio, que no Supabase quase não ajudou (14% de
  acertos), aqui teve 83% de acertos e 3.613 req/s: com milhares de leituras por segundo, os livros
  mais procurados (o k6 sorteia os livros com popularidade, como num catálogo real) são guardados
  nos primeiros segundos depois de o cache ser esvaziado. A taxa de acerto depende de quantas
  leituras se repetem dentro do TTL.
- **O N+1 continuou sendo o pior caso, mas sem colapso.** As 41 consultas do LAZY custam agora
  milissegundos, e ele atendeu 174 req/s com 50 VUs (p95 de 465 ms), contra 0,8 req/s no Supabase;
  com 100 e 200 VUs, ainda estourou os limites do k6 (p95 de 2,6 s com 200 VUs). Ficou 6,3 vezes
  abaixo do EAGER e 11,8 vezes abaixo da projeção, com a CPU da API no limite (380%): cada consulta
  tem um custo fixo no driver e no ORM, e o LAZY gastou 21,9 ms de CPU por requisição, contra 2,8 ms
  do EAGER.
- **As 178 colunas pesaram de verdade.** Sem a viagem dominando, a vazão passou a seguir a CPU que
  cada requisição gasta na API: EAGER, 1.101 req/s (2,8 ms de CPU por requisição); projeção, 2.057
  req/s (1,5 ms), 1,9 vezes o EAGER; SQL nativo, 2.470 req/s (1,1 ms). No Supabase, as três ficavam
  entre 72 e 74 req/s. O SQL nativo, que faz a mesma consulta da projeção, passou a ganhar dela: o
  trabalho que o SQLAlchemy faz para montar a consulta e ler as linhas, invisível perto de 155 ms de
  viagem, vira diferença de vazão quando a CPU da API é o limite.
- **O índice teve o maior ganho do trabalho.** Sem índice, cada consulta varre a tabela inteira
  (12.004 páginas), e as varreduras tomaram a máquina: o banco usou 531% de CPU, quase as 6 CPUs,
  contra 36% da API; o banco executando chegou a 1.080% (mais consultas em execução que CPUs,
  esperando a vez), e a vazão parou em 123 req/s. Com o índice, 2.488 req/s: 20 vezes mais, contra 2
  vezes no Supabase, e o gargalo voltou a ser a CPU da API.

**O que muda com o gargalo.** No Supabase, onde o custo é o número de viagens, a ordem dos ganhos
com 50 VUs foi: cache (263 vezes), eliminar o N+1 (93 vezes), índice (2 vezes) e projeção (quase
nada na vazão). Com o banco local, onde o custo é CPU, a ordem se inverteu em parte: índice (20
vezes), eliminar o N+1 (12 vezes), cache (4,4 vezes) e projeção (1,9 vezes). As otimizações são as
mesmas; o ganho de cada uma depende de onde está o gargalo, e por isso ele precisa ser medido, não
suposto.

**Observações sobre a execução.** A matriz parou uma vez, na execução 14 de 27, quando o Docker
falhou ao recriar o contêiner da API; ela foi retomada com `--continuar`, que pula as execuções já
gravadas, e o `executar.py` passou a tentar de novo antes de desistir. O banco local divide a
máquina com a API e o k6: a CPU que ele usa (de 50% a 139% nas versões rápidas) deixa de estar
disponível para a API, mas todas as versões rodaram nas mesmas condições, e a comparação entre elas
continua justa. Outros contêineres da máquina, de fora do trabalho, usaram 2,3% de uma CPU em média
(no máximo 30%, numa execução).

## 6. Discussão

**Qual técnica apresentou os maiores ganhos de desempenho?** O cache, quando acerta: com 50 VUs, a
ficha passou de 26 para 6.765 req/s (263 vezes) e de 2.000 para 7,3 ms de latência média, sem
nenhuma consulta ao banco. Em seguida vem a eliminação do N+1: com 10 VUs, a página de 20
empréstimos passou de 0,8 req/s e 11,4 s de latência média (LAZY) para 38 a 51 req/s e 0,20 a
0,27 s com uma consulta só; com 500 empréstimos e uma requisição por vez, de 157 s para 0,17 s
(seção 4.3). O índice teve o menor ganho relativo, mas foi a única otimização que tirou trabalho do
próprio banco: o dobro da vazão com 50 VUs e um tempo de execução por consulta 16 vezes menor (de
159 para 10 ms, segundo o `pg_stat_statements`). A ordem depende do gargalo: com o banco na mesma
máquina (seção 5.4), o índice deu o maior ganho (20 vezes mais vazão), e o cache, 4,4 vezes.

**Os ganhos foram mantidos quando a carga aumentou?** Sim, e em geral cresceram, porque as versões
sem otimização saturam primeiro. Sem cache, a vazão parou entre 21 e 26 req/s e a latência média
foi de 0,59 s para 8,5 s entre 10 e 200 VUs; o cache quente sustentou de 5.800 a 6.800 req/s com
latência média abaixo de 31 ms. O LAZY entrou em colapso (com 200 VUs, nenhuma resposta dentro da
janela em duas das três repetições), enquanto as versões de uma consulta mantiveram de 62 a
75 req/s. A vantagem da projeção sobre o EAGER também apareceu com a carga: do empate na vazão com
50 VUs a 75 contra 62 req/s com 200 VUs (parte disso, numa lentidão da instância; seção 5.3). Sem
índice, o banco saturou em ~36 req/s; com ele, a API chegou ao teto das conexões, com o dobro da
vazão em todos os níveis a partir de 50 VUs. A exceção é o cache frio: o ganho dele depende da taxa
de acerto (de 9% a 14% em 30 s), não da carga.

**Houve diferenças relevantes entre latência média, p95 e p99?** Sem saturação, pouca: com 10 VUs,
a versão otimizada teve média de 198 ms, p95 de 289 ms e p99 de 370 ms. Saturado, a cauda se
afasta muito da média: sem cache com 100 VUs, média de 4,1 s, p95 de 9,1 s e p99 de 12,6 s; nas
versões de uma consulta com 200 VUs, média de 2,7 a 3,2 s e p99 de 8,5 a 10,6 s. A espera não é
igual para todos: cada VU mantém a sua conexão com um dos quatro processos da API, e cada processo
tem só três conexões com o banco; quem cai num processo com mais VUs espera mais. No cache quente a
cauda continuou curta (p99 de 78 ms com 200 VUs), porque a fila é de CPU, e não de conexões. Em
alguns casos, a diferença entre as versões só apareceu na cauda: com 50 VUs, o EAGER e a projeção
tiveram médias quase iguais (703 e 684 ms), mas p95 de 1.100 e 843 ms. A média sozinha esconderia
justamente o que os usuários mais lentos sentem; por isso os limites do k6 foram definidos sobre o
p95 e o p99.

**Alguma otimização apresentou resultados inferiores aos esperados?** Sim:

- a projeção (8 colunas no lugar de 178) lê 28 vezes menos dados que o EAGER, mas sob carga a
  vazão quase não mudou até 50 VUs (74 contra 72 req/s) e, com 200 VUs, subiu 21%: o gargalo
  continuou sendo o número de conexões vezes a viagem até o banco, não o volume de dados. O ganho
  apareceu na latência com pouca carga (198 contra 268 ms com 10 VUs), na cauda (p95 23% menor com
  50 VUs) e nos recursos (metade da CPU da API). O SQL nativo, que faz a mesma consulta da
  projeção, não ganhou dela: escrever o SQL à mão não acelera uma consulta que o ORM já gera bem.
  Com o banco local (seção 5.4), em que o gargalo passou a ser a CPU da API, os dois ganhos
  apareceram: a projeção atendeu 1,9 vezes o EAGER, e o SQL nativo, 20% mais que a projeção;
- o cache frio, com 9% a 14% de acertos, quase não aliviou o banco: com 10 VUs, a vazão foi a
  mesma de sem cache;
- o índice, medido com uma requisição por vez, reduziu o histórico na API de 227 para 158 ms
  (seção 4.5), muito menos que as 100 vezes medidas no banco, porque a viagem domina; o tamanho real
  do ganho só apareceu sob carga;
- o `selectinload`, um EAGER sem N+1, fez 3 consultas e ficou quase três vezes mais lento que o
  JOIN (478 contra 164 ms com 10 empréstimos, seção 4.3): com o banco longe, cada consulta a mais
  pesa.

**Quais foram os principais gargalos identificados?**

1. A ida e volta até o banco, ~155 ms por comando SQL, que domina o tempo de toda requisição que
   consulta o banco.
2. As 12 conexões com o banco, que fixam o teto de vazão em 12 ÷ (consultas × 0,155 s): 77, 26 e
   menos de 2 req/s para 1, 3 e 41 consultas por requisição.
3. A CPU do banco, quando cada consulta percorre a tabela inteira (sem índice: seis varreduras
   ao mesmo tempo, em média, e ~36 req/s).
4. A CPU da API, quando o banco sai do caminho (cache quente: de 300% a 320% dos 400% possíveis
   com quatro processos). O k6 roda na mesma máquina e, nesse cenário, usou mais ~145% de um núcleo.
   Com o banco local (seção 5.4), ela passou a ser o gargalo de quase todas as versões.
5. O volume de dados, quando a consulta traz entidades inteiras: com as 178 colunas, o EAGER
   prendeu cada conexão por mais tempo que a projeção e usou o dobro da CPU da API.

Cada otimização eliminou um gargalo e revelou o seguinte: o cache trocou a fila por conexões pela
fila de CPU da API; o índice trocou a CPU do banco pelo teto das conexões; eliminar o N+1 trocou as
41 viagens por requisição pelo mesmo teto.

**Como a redução das consultas ao banco influenciou o desempenho?** Foi o fator dominante. Com cada
comando custando uma viagem, o tempo de uma requisição é, quase todo, o número de consultas vezes
155 ms, e a vazão máxima é inversamente proporcional a ele. De 41 consultas (LAZY) para 1, a
latência média com 10 VUs caiu de 11,4 s para 0,20 a 0,27 s e o teto subiu de menos de 2 para 77
req/s; de 3 consultas para nenhuma (acerto no cache), a vazão foi de 26 para 6.765 req/s. Já
acelerar cada consulta só fez diferença quando o banco estava saturado, como no caso do índice.
Neste ambiente, reduzir viagens valeu mais que reduzir o trabalho de cada consulta. Com o banco
na mesma máquina (seção 5.4), quando o gargalo passou a ser a CPU, reduzir trabalho valeu mais:
o índice deu 20 vezes mais vazão, e a projeção, 1,9 vezes a do EAGER.

**Quais são os possíveis custos ou riscos das otimizações adotadas?** Cada otimização troca um
custo por outro (*trade-off*): o cache troca atualidade dos dados por velocidade, a projeção troca
flexibilidade por eficiência, o SQL nativo troca portabilidade e conferência pelo ORM por
controle, e o índice troca escrita e espaço por leitura.

- *Cache*: dados desatualizados durante o TTL (seção 3.4); a invalidação precisa existir em toda
  rota que altera os dados, inclusive nas que forem criadas depois; mais um serviço para operar;
  memória (25 MB para as 20.000 fichas); e o cache frio depois de um reinício ou de uma
  invalidação em massa, quando o banco volta a receber toda a carga, como mostrou o cenário do
  cache frio. Se o Redis cair, a ficha passa a vir do banco (seção 3.6): a API continua
  respondendo, sem erros, mas com o desempenho de sem cache, e o banco precisa aguentar a carga
  inteira enquanto isso.
- *EAGER no mapeamento*: vale para todas as consultas da entidade, inclusive as que não usam os
  relacionamentos (as versões "resumo" da seção 4.3 leram 10 vezes mais dados); com coleções, o
  JOIN multiplica as linhas da consulta principal.
- *Projeções*: uma consulta e um formato de resposta por tela, e o resultado não é uma entidade:
  não dá para alterá-lo e salvá-lo pelo ORM. O *SQL nativo* ainda perde a conferência do ORM e a
  portabilidade entre bancos (seção 4.4).
- *Índices*: espaço (9 MB para o índice proposto), escrita mais cara (+44% por `INSERT` com um
  índice, +99% com três) e mais trabalho de `VACUUM`; e o plano depende da configuração do banco
  (`random_page_cost`), não só do índice.
- *Tabelas largas*: toda consulta que carrega a entidade inteira paga por todas as colunas. Quanto
  mais larga a tabela, mais importa buscar só o que a resposta usa.

**Limitações.**

- O banco fica a ~155 ms da API, numa instância compartilhada do plano gratuito. Os resultados
  valem para esse ambiente: com o banco na mesma rede, a viagem cairia para menos de 1 ms, o N+1
  continuaria sendo o pior caso, mas o volume das 178 colunas e o índice pesariam mais em relação à
  viagem. A seção 5.4 mediu esse outro extremo, com o banco na mesma máquina: o índice passou a dar
  20 vezes mais vazão, a projeção 1,9 vezes a do EAGER, e o cache, só 4,4 vezes. A instância também teve trechos lentos, em níveis isolados de algumas execuções
  (seção 5.3).
- O k6 roda na mesma máquina que a API e disputa a CPU com ela no cenário do cache quente: a vazão
  desse cenário é um limite inferior do que a API atenderia sozinha.
- A CPU do servidor do banco não é acessível no Supabase; o comportamento dele foi medido pelo
  `pg_stat_statements`.
- Janelas de 30 s e três repetições bastam para as diferenças grandes deste trabalho, mas a
  variação entre repetições passou de 15% em alguns níveis, principalmente com 10 VUs. Diferenças
  de poucos por cento, como entre a projeção e o SQL nativo, não são conclusivas.

## 7. Conclusão

As três técnicas melhoraram o desempenho, cada uma de um jeito, e as medições mostraram por quê.
Com o banco a ~155 ms da API, o custo de uma requisição é praticamente o número de viagens até o
banco, e a capacidade da API é o número de conexões dividido pelo tempo que cada requisição as
prende. Daí os principais resultados:

- o **cache** teve o maior ganho (de 26 para 6.765 req/s com 50 VUs) porque elimina as viagens,
  mas só no acerto: com o cache frio o ganho foi pequeno, e o preço é aceitar dados desatualizados
  por até um TTL. O que vai para o cache foi decidido pela volatilidade: a ficha vai, a
  disponibilidade não;
- o **N+1** do LAZY transformou uma página de 20 empréstimos em 41 consultas e 11 s de espera, e a
  API não sustentou nem 10 usuários. Declarar EAGER ou LAZY não diz quantas consultas serão feitas:
  o `joined` fez 1, o `selectinload` 3 e o `immediateload` 41. A regra que fica é manter o
  mapeamento LAZY e pedir o carregamento antecipado em cada consulta que precisa dele;
- as **tabelas largas** mostraram o custo de carregar entidades inteiras: 178 colunas para usar 8.
  A projeção leu 28 vezes menos dados e gastou metade da CPU da API; com páginas de 500
  empréstimos, respondeu em 169 ms contra 245 ms do EAGER. Sob carga, com páginas de 20, a vazão
  quase não mudou até 50 VUs, porque o gargalo era outro, mas a cauda sim (p95 de 843 contra
  1.100 ms), e com 200 VUs a projeção atendeu 21% mais. Uma otimização só chega inteira ao usuário
  quando ataca o gargalo da vez;
- o **índice** quase não mudou uma consulta isolada, porque a viagem domina, mas sob carga tirou o
  banco da saturação: o dobro da vazão com 50 VUs. O `EXPLAIN ANALYZE` mostrou que ele é usado e
  como, e o custo de escrita mostrou por que não vale indexar todas as colunas;
- o **banco local** (seção 5.4) mostrou que o ganho de cada técnica depende do gargalo: sem a viagem,
  o índice passou a dar o maior ganho (20 vezes), a projeção chegou a 1,9 vezes a
  vazão do EAGER, e o cache caiu para 4,4 vezes.

**Como demonstrar, por meio de evidências, que uma mudança realmente melhorou o desempenho de um
sistema?** É a pergunta que o enunciado deixa para o fim, e a resposta deste trabalho é o próprio
método: identificar o problema, implementar uma alternativa, medir, comparar e justificar. Na
prática, foi preciso medir as versões no mesmo ambiente, com as mesmas cargas, aquecimento e
repetições; olhar os percentis, porque a média esconde a cauda; acompanhar os recursos (consultas,
CPU, memória, banco), e não só o tempo de resposta; e explicar o mecanismo por trás de cada número.
Sem isso, a projeção pareceria inútil e o índice, irrelevante; com isso, fica claro onde cada um
ajuda e qual é o próximo gargalo.

## Como executar

### Pré-requisitos

- Docker com Docker Compose (no Windows, o Docker Desktop). É o único requisito para subir a API
  e rodar os testes de carga: o k6 e o `psql` rodam em contêineres.
- Um projeto no Supabase (o plano gratuito basta), para o banco. Sem ele, dá para usar um
  PostgreSQL local, num contêiner (fim do passo 1).
- Python 3.10 ou mais novo, só para os roteiros de experimento e o roteiro dos testes de carga.
  Eles usam apenas a biblioteca padrão; não há nada para instalar com o pip.
- Opcional: o [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) instalado na máquina,
  para rodar os scripts fora do Docker.

### 1. Preparar o banco

```bash
git clone https://github.com/MarcosFelipeFP/trabalho-a2-otimizacao-web-services.git
cd trabalho-a2-otimizacao-web-services
cp .env.exemplo .env
```

No `.env`, preencha os dados do projeto no Supabase, que ficam no painel, em **Connect** >
**Session pooler**: o endereço (`PGHOST`), o usuário (`PGUSER`, no formato
`postgres.<id do projeto>`) e a senha do banco (`PGPASSWORD`). O `.env` não vai para o Git.

Depois, crie as tabelas e gere os dados (cerca de 75 segundos):

```bash
docker compose run --rm psql -f /banco/01-esquema.sql -f /banco/02-dados.sql -f /banco/03-indices.sql
```

No Git Bash do Windows, rode antes `export MSYS_NO_PATHCONV=1`, para ele não reescrever os caminhos
que começam com `/`. Para voltar ao estado inicial (dados recém-gerados, sem índices de
experimento), apague as tabelas e repita o comando acima:

```bash
docker compose run --rm psql -c "DROP TABLE emprestimo, livro, leitor, autor, categoria"
```

**Sem Supabase.** Sem o `.env`, a API usa um PostgreSQL 17 local, num contêiner do perfil
`banco-local`, que cria as tabelas e gera os dados sozinho na primeira subida:
`docker compose --profile banco-local up -d --build` (para recomeçar do zero,
`docker compose --profile banco-local down -v`). Os números deste relatório foram medidos com o
banco no Supabase, menos os da seção 5.4 e os do teste sob carga da seção 3.6; com o banco local,
os tempos são bem menores, porque a ida e volta até o banco cai de ~160 ms para menos de 1 ms.

### 2. Subir o cache e a API

```bash
docker compose up -d --build
```

A documentação interativa fica em <http://localhost:8000/docs>, onde dá para chamar todas as rotas
sem Postman, e o painel de demonstração, em <http://localhost:8000/painel/> (a raiz,
<http://localhost:8000>, leva até ele). Alguns exemplos com curl:

```bash
curl -i http://localhost:8000/api/livros/42/com-cache          # X-Cache: MISS e depois HIT
curl -i -X PUT http://localhost:8000/api/livros/42 -H "Content-Type: application/json" -d '{"titulo": "Novo título"}'
curl -i "http://localhost:8000/api/emprestimos/lazy?desde_id=1000&quantidade=20"    # X-Consultas-SQL: 41
curl -i "http://localhost:8000/api/emprestimos/eager?desde_id=1000&quantidade=20"   # X-Consultas-SQL: 1
curl "http://localhost:8000/api/laboratorio/sql/emprestimos/lazy?quantidade=3"      # o SQL executado
curl http://localhost:8000/api/leitores/150/emprestimos
curl "http://localhost:8000/api/laboratorio/explain/historico?leitor_id=150"        # EXPLAIN ANALYZE
```

As variáveis `CACHE_TTL_SEGUNDOS` (padrão 600), `CACHE_TEMPO_LIMITE_S` (quanto esperar o Redis
antes de buscar a ficha no banco, padrão 0,5), `WORKERS` (processos da API, padrão 4) e
`CONEXOES_POR_WORKER` (padrão 3) mudam a configuração: por exemplo,
`CACHE_TTL_SEGUNDOS=30 docker compose up -d api`. Com o Supabase, `WORKERS` × `CONEXOES_POR_WORKER`
deve ficar abaixo de 15, o limite do pooler, com folga para o `psql` dos roteiros.

### 3. Experimentos dos itens 1 e 2

Com a API no ar, na pasta do projeto:

```bash
python experimentos/cache.py          # experimento obrigatório do cache (3.4) e tempos com e sem cache
python experimentos/carregamento.py   # LAZY, EAGER e otimizadas com 10 a 500 empréstimos (4.3 e 4.4)
python experimentos/indices.py        # planos de execução, índices e custo de escrita (seção 5)
python experimentos/falha_do_cache.py # o Redis fora do ar: a ficha vem do banco (3.6)
```

Com o banco no Supabase, o roteiro do cache leva uns 6 minutos, o de carregamento uns 20 (cada
requisição do LAZY com 500 empréstimos leva dois minutos e meio), o de índices uns 5 e o da falha
do Redis menos de 2. O da falha do Redis para, congela e sobe de novo o contêiner do Redis. Eles
gravam tabelas em Markdown, o SQL gerado e os planos de execução em `experimentos/resultados/`. O
banco e a API voltam ao estado inicial no fim.

### 4. Testes de desempenho (k6)

Um cenário avulso, com o painel web do k6 ao vivo em <http://localhost:5665>:

```bash
docker compose run --rm --service-ports -e K6_WEB_DASHBOARD=true k6 run k6/cache.js -e VERSAO=com-cache-quente
docker compose run --rm k6 run k6/persistencia.js -e VERSAO=lazy -e CARGAS=10,50
docker compose run --rm k6 run k6/indice.js -e VERSAO=com-indice
```

A ficha com cache sob carga, com o Redis parado (seção 3.6):

```bash
docker compose stop cache
docker compose run --rm k6 run k6/cache.js -e VERSAO=redis-fora
docker compose start cache
```

Os números da seção 3.6 vêm de três execuções assim, alternadas com três da versão
`sem-cache`, com a API recriada antes de cada uma e o banco local (abaixo, junto da matriz da
seção 5.4, está como apontar a API para ele).

A matriz completa, com repetições, medição de CPU e memória e geração de tabelas e gráficos:

```bash
python testes-carga/executar.py            # cerca de 2 horas; deixe a máquina sem outras tarefas
python testes-carga/executar.py --rapido   # conferência do roteiro, uns 15 minutos
```

A matriz da seção 5.4, com o banco local (no bash). As variáveis do ambiente valem mais que as do
`.env`, e o `executar.py` recria a API com elas:

```bash
docker compose --profile banco-local up -d banco
PGHOST=banco PGPORT=5432 PGUSER=biblioteca PGPASSWORD=biblioteca PGDATABASE=biblioteca PGSSLMODE=disable \
  python testes-carga/executar.py --cenarios cache,persistencia,indice
```

Para um teste avulso com o banco local, como o do Redis parado, as mesmas variáveis vão na frente
de `docker compose up -d --force-recreate api`; o mesmo comando sem elas devolve a API ao Supabase.

A matriz também pode rodar em partes: `--minutos 9` faz o roteiro parar antes de começar uma
execução que passaria desse tempo, e `--continuar testes-carga/resultados/<data e hora>` retoma
de onde parou, com os parâmetros da primeira parte. As tabelas e os gráficos podem ser refeitos a
qualquer momento com `python testes-carga/analisar.py testes-carga/resultados/<data e hora>`.

Os resultados ficam em `testes-carga/resultados/<data e hora>/`: `resumo.md` com as tabelas,
`graficos/`, `execucoes.csv` (uma linha por nível de carga de cada execução), o resumo de cada
execução do k6 (`k6/`), o relatório HTML do painel web do k6 da primeira repetição de cada versão
(`html/`), os comandos SQL de cada execução segundo o `pg_stat_statements` (`banco/`), a taxa de
acerto do cache segundo a segundo (`cache/`) e o ambiente da medição (`ambiente.json`).

### 5. Roteiro para a apresentação

Uma sequência de uns 7 minutos que cobre o que a 7.3 do enunciado pede, com a API no ar:

1. **Arquitetura**: o diagrama da seção 2 e `docker compose ps` (API e Redis nesta máquina; o
   banco no Supabase).
2. **Web Services**: `GET /api/livros/42/sem-cache` pela documentação interativa
   (<http://localhost:8000/docs>).
3. **Cache e atualização**: a ficha com cache duas vezes (`X-Cache: MISS` e depois `HIT`; de meio
   segundo para menos de 1 ms), um `PUT` (`X-Cache-Invalidado: sim`) e a ficha de novo, já com o
   título novo. Se sobrar tempo, a queda do Redis: no painel, "Travar o Redis por 15 s", a ficha
   com cache (`X-Cache: INDISPONIVEL`, ainda 200), um `PUT` (`X-Cache-Invalidado: pendente`) e, quando
   o Redis volta, a ficha com o título novo (MISS).
4. **LAZY e EAGER**: `X-Consultas-SQL` da página de 20 empréstimos em `/api/emprestimos/lazy` e
   `/eager` (41 contra 1) e o SQL de cada uma em `/api/laboratorio/sql/emprestimos/lazy?quantidade=3`.
5. **Consulta otimizada**: o SQL da versão `otimizada`, com 8 colunas no lugar das 178 do EAGER.
6. **Índices**: `GET /api/laboratorio/explain/historico?leitor_id=150` (Seq Scan), depois
   `PUT /api/laboratorio/indices/leitor-data` e o mesmo `EXPLAIN` (Index Scan); no fim, `DELETE`
   no mesmo endereço do índice.
7. **Teste de desempenho**: um cenário com o painel do k6 ao vivo em <http://localhost:5665>.
8. **Resultados**: as tabelas e os gráficos da seção 5.3 e a discussão.

O painel (<http://localhost:8000/painel/>) acompanha o roteiro inteiro, uma seção por passo: Visão
geral (1), Cache (3, com o experimento da 3.4 completo e a queda do Redis), LAZY × EAGER (4 e 5), Índices (6), Testes
de carga (7, com o comando para copiar e o link do painel do k6) e Resultados e conclusões (8). O
rodapé mostra cada chamada HTTP com os cabeçalhos de medição (2).

```bash
curl -s -D - -o /dev/null http://localhost:8000/api/livros/42/com-cache | grep -i -E "^(x-cache|server-timing)"
curl -s -D - -o /dev/null -X PUT http://localhost:8000/api/livros/42 -H "Content-Type: application/json" -d '{"titulo": "Novo título"}' | grep -i x-cache-invalidado
curl -s -D - -o /dev/null "http://localhost:8000/api/emprestimos/lazy?desde_id=1000&quantidade=20" | grep -i x-consultas-sql
docker compose run --rm --service-ports -e K6_WEB_DASHBOARD=true k6 run k6/cache.js -e VERSAO=com-cache-quente -e CARGAS=50
```

O `PUT` altera o livro 42 de verdade; para voltar ao estado inicial, recarregue o banco (passo 1).

## Estrutura do repositório

```
api/                  Web Services (FastAPI + SQLAlchemy)
  app/modelos.py      mapeamento das tabelas, com a versão LAZY e a EAGER do empréstimo
  app/rotas/          livros (cache), emprestimos (EAGER x LAZY), leitores (índice) e laboratório
  app/cache.py        cache das fichas no Redis, com a queda para o banco se ele falhar
  app/medicao.py      contagem de comandos SQL e tempos de cada requisição
  app/painel/         painel de demonstração (HTML, CSS e JavaScript), servido em /painel
banco/                criação das tabelas e geração dos dados (semente fixa), executadas pelo psql
  experimentos/       índices do experimento da seção 5, para execução manual
experimentos/         roteiros dos experimentos dos itens 1 e 2 e os resultados deles
testes-carga/
  k6/                 scripts do k6: cache.js, persistencia.js, indice.js e comum.js
  executar.py         roteiro que roda a matriz de testes de carga
  analisar.py         tabelas e gráficos a partir dos resultados
  graficos.py         gráficos em SVG, sem dependências externas (usado pelo analisar.py)
  resultados/         as matrizes do relatório (Supabase e banco local) e a carga com o Redis parado
docker-compose.yml    cache (Redis), API, k6, psql e o PostgreSQL local opcional
.env.exemplo          modelo do .env com a conexão ao banco no Supabase
```

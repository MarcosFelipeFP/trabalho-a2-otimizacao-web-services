Banco: PostgreSQL local (perfil banco-local). Tempo limite do Redis na API: 0,5 s; vigia a cada 1,0 s. O tempo (t) conta a partir da queda do Redis.

### A. Redis parado (`docker compose stop cache`)

| passo | t (s) | operação | status | X-Cache | consultas SQL | tempo no servidor (ms) | título devolvido | o que aconteceu |
|---|---:|---|---|---|---:|---:|---|---|
| A1 | 0,0 | GET com cache, Redis no ar | 200 | MISS | 3 | 4,65 | A Biblioteca Eterna dos Esquecidos | falha: monta a ficha no banco e guarda |
| A2 | 0,0 | GET com cache de novo | 200 | HIT | 0 | 0,72 | A Biblioteca Eterna dos Esquecidos | acerto: nenhuma consulta ao banco |
| A3 | 0,0 | docker compose stop cache | – | – | – | – | – | o contêiner do Redis parou (0,6 s) |
| A4.1 | 3,3 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 3.332,27 | A Biblioteca Eterna dos Esquecidos | espera a falha aparecer e vai ao banco |
| A4.2 a A4.10 | 3,3 a 3,4 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 4,11 | A Biblioteca Eterna dos Esquecidos | direto ao banco, sem tentar o Redis (mediana de 9) |
| A5.1 a A5.10 | 3,4 a 3,4 | GET sem cache, para comparar | 200 | – | 3 | 3,79 | A Biblioteca Eterna dos Esquecidos | sempre do banco (mediana de 10) |
| A6 | 3,4 | PUT /api/livros/{id} (novo título) | 200 | invalidado: pendente | 5 | 10,70 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | a alteração vale; a invalidação fica pendente |
| A7 | 3,4 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 4,01 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | já com o título novo, do banco |
| A8 | 3,9 | docker compose start cache | – | – | – | – | – | o contêiner do Redis subiu de novo, vazio (0,4 s) |
| A9 | 4,4 | GET com cache, Redis de volta | 200 | MISS | 3 | 4,41 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | o cache voltou 0,5 s depois do start (1 leitura ainda do banco antes) |
| A10 | 4,4 | GET com cache de novo | 200 | HIT | 0 | 0,67 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | acerto: o cache voltou ao normal |

### B. Redis travado por 10 s (`docker compose pause cache`), com os dados na memória

| passo | t (s) | operação | status | X-Cache | consultas SQL | tempo no servidor (ms) | título devolvido | o que aconteceu |
|---|---:|---|---|---|---:|---:|---|---|
| B1 | 0,0 | GET com cache, Redis no ar | 200 | HIT | 0 | 0,66 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | a ficha está no cache |
| B2 | 0,0 | docker compose pause cache | – | – | – | – | – | o Redis congela: as conexões continuam abertas, sem resposta (0,2 s) |
| B3 | 0,5 | GET com cache, Redis travado | 200 | INDISPONIVEL | 3 | 505,52 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | espera o tempo limite e vai ao banco |
| B4 | 0,5 | PUT /api/livros/{id} (novo título) | 200 | invalidado: pendente | 5 | 11,22 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | a alteração vale; a invalidação fica pendente |
| B5.1 a B5.19 | 0,5 a 9,6 | GET com cache, Redis travado | 200 | INDISPONIVEL | 3 | 3,98 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | título novo, do banco, sem tentar o Redis (mediana de 19) |
| B6 | 10,3 | docker compose unpause cache | – | – | – | – | – | o Redis volta, com a ficha antiga na memória (0,2 s) |
| B7 | 10,8 | GET com cache, Redis de volta | 200 | MISS | 3 | 5,15 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | MISS com o título novo: a ficha antiga foi apagada antes de o cache voltar; 0,5 s depois do unpause (1 leitura ainda do banco antes) |
| B8 | 10,8 | GET com cache de novo | 200 | HIT | 0 | 0,86 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | acerto, com o título novo |

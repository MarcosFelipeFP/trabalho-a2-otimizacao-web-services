Banco: Supabase (aws-1-us-east-2.pooler.supabase.com). Tempo limite do Redis na API: 0,5 s; vigia a cada 1,0 s. O tempo (t) conta a partir da queda do Redis.

### A. Redis parado (`docker compose stop cache`)

| passo | t (s) | operação | status | X-Cache | consultas SQL | tempo no servidor (ms) | título devolvido | o que aconteceu |
|---|---:|---|---|---|---:|---:|---|---|
| A1 | 0,5 | GET com cache, Redis no ar | 200 | MISS | 3 | 489,62 | A Biblioteca Eterna dos Esquecidos | falha: monta a ficha no banco e guarda |
| A2 | 0,5 | GET com cache de novo | 200 | HIT | 0 | 0,64 | A Biblioteca Eterna dos Esquecidos | acerto: nenhuma consulta ao banco |
| A3 | 0,0 | docker compose stop cache | – | – | – | – | – | o contêiner do Redis parou (1,6 s) |
| A4.1 | 8,4 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 8.452,57 | A Biblioteca Eterna dos Esquecidos | espera a falha aparecer e vai ao banco |
| A4.2 a A4.10 | 8,9 a 12,8 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 478,99 | A Biblioteca Eterna dos Esquecidos | direto ao banco, sem tentar o Redis (mediana de 9) |
| A5.1 a A5.10 | 13,3 a 17,7 | GET sem cache, para comparar | 200 | – | 3 | 485,61 | A Biblioteca Eterna dos Esquecidos | sempre do banco (mediana de 10) |
| A6 | 18,9 | PUT /api/livros/{id} (novo título) | 200 | invalidado: pendente | 5 | 1.188,21 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | a alteração vale; a invalidação fica pendente |
| A7 | 19,4 | GET com cache, Redis parado | 200 | INDISPONIVEL | 3 | 488,47 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | já com o título novo, do banco |
| A8 | 19,7 | docker compose start cache | – | – | – | – | – | o contêiner do Redis subiu de novo, vazio (0,4 s) |
| A9 | 25,2 | GET com cache, Redis de volta | 200 | MISS | 3 | 480,49 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | o cache voltou 5,4 s depois do start (5 leituras ainda do banco antes) |
| A10 | 25,2 | GET com cache de novo | 200 | HIT | 0 | 0,76 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | acerto: o cache voltou ao normal |

### B. Redis travado por 10 s (`docker compose pause cache`), com os dados na memória

| passo | t (s) | operação | status | X-Cache | consultas SQL | tempo no servidor (ms) | título devolvido | o que aconteceu |
|---|---:|---|---|---|---:|---:|---|---|
| B1 | 0,0 | GET com cache, Redis no ar | 200 | HIT | 0 | 0,63 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | a ficha está no cache |
| B2 | 0,0 | docker compose pause cache | – | – | – | – | – | o Redis congela: as conexões continuam abertas, sem resposta (0,2 s) |
| B3 | 1,0 | GET com cache, Redis travado | 200 | INDISPONIVEL | 3 | 979,43 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis parado) | espera o tempo limite e vai ao banco |
| B4 | 2,1 | PUT /api/livros/{id} (novo título) | 200 | invalidado: pendente | 5 | 1.120,37 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | a alteração vale; a invalidação fica pendente |
| B5.1 a B5.9 | 2,6 a 10,4 | GET com cache, Redis travado | 200 | INDISPONIVEL | 3 | 478,81 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | título novo, do banco, sem tentar o Redis (mediana de 9) |
| B6 | 11,1 | docker compose unpause cache | – | – | – | – | – | o Redis volta, com a ficha antiga na memória (0,2 s) |
| B7 | 12,6 | GET com cache, Redis de volta | 200 | MISS | 3 | 479,33 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | MISS com o título novo: a ficha antiga foi apagada antes de o cache voltar; 1,5 s depois do unpause (1 leitura ainda do banco antes) |
| B8 | 12,6 | GET com cache de novo | 200 | HIT | 0 | 0,51 | A Biblioteca Eterna dos Esquecidos (alterado com o Redis travado) | acerto, com o título novo |

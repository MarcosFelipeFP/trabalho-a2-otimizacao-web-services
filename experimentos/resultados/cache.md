### Experimento passo a passo (livro 42, TTL de 20 s)

| passo | operação | X-Cache | consultas SQL | tempo no servidor (ms) | título devolvido | ficha gerada às | TTL restante | o que aconteceu |
|---|---|---|---:|---:|---|---|---:|---|
| 1 | GET com cache (cache vazio) | MISS | 3 | 2,97 | A Biblioteca Eterna dos Esquecidos | 23:33:02.697 | 20 s | falha: monta a ficha no banco e guarda |
| 2 | GET com cache de novo | HIT | 0 | 0,37 | A Biblioteca Eterna dos Esquecidos | 23:33:02.697 | 20 s | acerto: nenhuma consulta ao banco |
| 3 | PUT /api/livros/{id} (novo título) | – | 5 | 5,26 | A Biblioteca Eterna dos Esquecidos (edição revista) | – | – | ficha removida do cache (X-Cache-Invalidado: sim) |
| 4a | GET com cache depois do PUT | MISS | 3 | 2,72 | A Biblioteca Eterna dos Esquecidos (edição revista) | 23:33:02.710 | 20 s | falha: busca a versão nova no banco |
| 4b | GET com cache de novo | HIT | 0 | 0,36 | A Biblioteca Eterna dos Esquecidos (edição revista) | 23:33:02.710 | 20 s | acerto, já com o título novo |
| 5a | UPDATE direto no banco (por fora da API) | – | – | – | A Biblioteca Eterna dos Esquecidos (edição revista) [alterado direto no banco] | – | – | nada avisa o cache |
| 5b | GET com cache | HIT | 0 | 0,77 | A Biblioteca Eterna dos Esquecidos (edição revista) | 23:33:02.710 | 20 s | acerto com o título ANTIGO: dado desatualizado |
| 5c | GET com cache depois do TTL | MISS | 3 | 4,54 | A Biblioteca Eterna dos Esquecidos (edição revista) [alterado direto no banco] | 23:33:24.422 | 20 s | a ficha expirou: falha e título atual |

### Tempo de resposta sem e com cache (uma requisição por vez, 300 livros sorteados)

| situação | consultas SQL por requisição | acertos | servidor: mediana (ms) | servidor: p95 (ms) | total no cliente: mediana (ms) |
|---|---:|---:|---:|---:|---:|
| sem cache | 3,0 | 0 de 300 | 2,23 | 2,44 | 2,72 |
| com cache, falha (cache vazio) | 3,0 | 0 de 300 | 2,53 | 2,86 | 3,00 |
| com cache, acerto (mesmos livros de novo) | 0,0 | 300 de 300 | 0,37 | 0,46 | 0,85 |

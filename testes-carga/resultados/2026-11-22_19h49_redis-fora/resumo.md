# Ficha com cache e o Redis parado, sob carga

Execuções do k6 (`k6/cache.js`), alternadas: 3 da versão `sem-cache` e 3 da versão `redis-fora`
(rota com cache, com o contêiner do Redis parado por `docker compose stop cache` logo antes). Cada
execução recria a API antes, com o Redis no ar; 10 s de aquecimento e 30 s de medição por nível. Média das
repetições; variação: maior distância entre a vazão de uma repetição e a média. Ver README, seção 3.6.

| VUs | Sem cache: vazão | média | p95 | Redis parado: vazão | média | p95 | diferença na vazão | variação entre repetições (sem / parado) | erros com o Redis parado |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1.472 req/s | 6,7 ms | 13,8 ms | 1.372 req/s | 7,2 ms | 16,3 ms | −6,8% | ±6,9% / ±9,1% | 0,00% |
| 50 | 1.439 req/s | 35,1 ms | 76,0 ms | 1.469 req/s | 34,0 ms | 85,2 ms | +2,1% | ±15,1% / ±7,5% | 0,00% |
| 100 | 1.435 req/s | 69,7 ms | 156,8 ms | 1.405 req/s | 71,3 ms | 165,5 ms | −2,1% | ±4,3% / ±8,0% | 0,00% |
| 200 | 1.364 req/s | 148,0 ms | 341,0 ms | 1.378 req/s | 145,8 ms | 336,2 ms | +1,0% | ±12,9% / ±7,1% | 0,00% |

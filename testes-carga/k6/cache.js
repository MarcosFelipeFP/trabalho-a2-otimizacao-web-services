// Cenário 1 (seção 6.2): ficha do livro sem cache e com cache.
//
//   VERSAO=sem-cache          GET /api/livros/{id}/sem-cache: toda requisição consulta o banco
//   VERSAO=com-cache-frio     GET /api/livros/{id}/com-cache, com o cache esvaziado logo antes de
//                             cada medição: acertos e falhas enquanto o cache se enche
//   VERSAO=com-cache-quente   GET /api/livros/{id}/com-cache, com as fichas de todos os livros já
//                             guardadas antes do teste: só acertos
//   VERSAO=redis-fora         GET /api/livros/{id}/com-cache com o Redis parado (docker compose stop
//                             cache): a ficha vem do banco, com X-Cache: INDISPONIVEL (README, 3.6)
//
// Cada requisição sorteia um livro entre 1 e TOTAL_LIVROS (padrão 20000), com popularidade
// (idPopular, em comum.js): os livros mais procurados se repetem, como num catálogo real.
//
// Exemplo: k6 run -e VERSAO=com-cache-quente -e CARGAS=50 testes-carga/k6/cache.js
import {
  BASE_URL, concluirPreparo, consultar, idPopular, laboratorio, montarOpcoes, resumir,
} from './comum.js';

const VERSOES = ['sem-cache', 'com-cache-frio', 'com-cache-quente', 'redis-fora'];
const VERSAO = __ENV.VERSAO || 'com-cache-quente';
if (!VERSOES.includes(VERSAO)) {
  throw new Error(`VERSAO deve ser uma destas: ${VERSOES.join(', ')}`);
}
const TOTAL_LIVROS = Number(__ENV.TOTAL_LIVROS || 20000);
const ROTA = VERSAO === 'sem-cache' ? 'sem-cache' : 'com-cache';

export const options = montarOpcoes({
  exec: 'lerFicha',
  preparo: VERSAO === 'com-cache-frio' ? 'esvaziarCache' : null,
  cache: ROTA === 'com-cache',
});

export function setup() {
  if (VERSAO === 'redis-fora') {
    // com o Redis parado, as rotas de laboratório do cache respondem 503: só registra o estado
    return concluirPreparo({});
  }
  laboratorio('DELETE', '/api/laboratorio/cache');
  let enchimento = null;
  if (VERSAO === 'com-cache-quente') {
    // as 20.000 fichas montadas de uma vez pela rota de laboratório e gravadas no Redis
    enchimento = laboratorio('POST', '/api/laboratorio/cache/encher');
  }
  return concluirPreparo({ enchimento, cache: laboratorio('GET', '/api/laboratorio/cache') });
}

export function lerFicha() {
  const id = idPopular(TOTAL_LIVROS);
  consultar(`${BASE_URL}/api/livros/${id}/${ROTA}`, `GET /api/livros/{id}/${ROTA}`);
}

export function esvaziarCache() {
  laboratorio('DELETE', '/api/laboratorio/cache');
}

export function handleSummary(dados) {
  return resumir(dados, { cenario: 'cache', versao: VERSAO });
}

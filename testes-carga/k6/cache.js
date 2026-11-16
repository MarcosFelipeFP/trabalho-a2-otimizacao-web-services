// Cenário 1 (seção 6.2): ficha do livro sem cache e com cache.
//
//   VERSAO=sem-cache          GET /api/livros/{id}/sem-cache: toda requisição consulta o banco
//   VERSAO=com-cache-frio     GET /api/livros/{id}/com-cache, com o cache esvaziado logo antes de
//                             cada medição: acertos e falhas enquanto o cache se enche
//   VERSAO=com-cache-quente   GET /api/livros/{id}/com-cache, com as fichas de todos os livros já
//                             guardadas antes do teste: só acertos
//
// Cada requisição sorteia um livro entre 1 e TOTAL_LIVROS (padrão 20000).
//
// Exemplo: k6 run -e VERSAO=com-cache-quente -e CARGAS=50 testes-carga/k6/cache.js
import http from 'k6/http';
import {
  BASE_URL, concluirPreparo, consultar, idAleatorio, laboratorio, montarOpcoes, resumir,
} from './comum.js';

const VERSOES = ['sem-cache', 'com-cache-frio', 'com-cache-quente'];
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
  laboratorio('DELETE', '/api/laboratorio/cache');
  if (VERSAO === 'com-cache-quente') {
    encherCache();
  }
  return concluirPreparo({ cache: laboratorio('GET', '/api/laboratorio/cache') });
}

export function lerFicha() {
  const id = idAleatorio(TOTAL_LIVROS);
  consultar(`${BASE_URL}/api/livros/${id}/${ROTA}`, `GET /api/livros/{id}/${ROTA}`);
}

export function esvaziarCache() {
  laboratorio('DELETE', '/api/laboratorio/cache');
}

// Passa uma vez por todos os livros pela própria rota com cache, em lotes de requisições paralelas.
function encherCache() {
  const lote = 250;
  for (let inicio = 1; inicio <= TOTAL_LIVROS; inicio += lote) {
    const requisicoes = [];
    for (let id = inicio; id < inicio + lote && id <= TOTAL_LIVROS; id++) {
      requisicoes.push([
        'GET', `${BASE_URL}/api/livros/${id}/com-cache`, null,
        { tags: { name: 'preparo: encher o cache', tipo: 'preparo' } },
      ]);
    }
    http.batch(requisicoes);
  }
}

export function handleSummary(dados) {
  return resumir(dados, { cenario: 'cache', versao: VERSAO });
}

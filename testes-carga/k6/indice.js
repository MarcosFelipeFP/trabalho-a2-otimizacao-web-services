// Cenário 3 (seção 6.2): histórico de empréstimos de um leitor, antes e depois do índice
// idx_emprestimo_leitor_data ON emprestimo (leitor_id, data_emprestimo DESC).
//
//   VERSAO=sem-indice   remove o índice antes do teste (estado inicial do banco)
//   VERSAO=com-indice   cria o índice antes do teste; no fim ele é removido de novo
//
// Cada requisição sorteia um leitor entre 1 e TOTAL_LEITORES (padrão 10000).
//
// Exemplo: k6 run -e VERSAO=com-indice -e CARGAS=50 testes-carga/k6/indice.js
import {
  BASE_URL, concluirPreparo, consultar, idAleatorio, laboratorio, montarOpcoes, resumir,
} from './comum.js';

const VERSOES = ['sem-indice', 'com-indice'];
const VERSAO = __ENV.VERSAO || 'sem-indice';
if (!VERSOES.includes(VERSAO)) {
  throw new Error(`VERSAO deve ser uma destas: ${VERSOES.join(', ')}`);
}
const TOTAL_LEITORES = Number(__ENV.TOTAL_LEITORES || 10000);

export const options = montarOpcoes({ exec: 'historico' });

export function setup() {
  // nenhum outro índice em emprestimo(leitor_id) pode estar no caminho
  laboratorio('DELETE', '/api/laboratorio/indices/leitor');
  laboratorio(VERSAO === 'com-indice' ? 'PUT' : 'DELETE', '/api/laboratorio/indices/leitor-data');
  return concluirPreparo();
}

export function historico() {
  const id = idAleatorio(TOTAL_LEITORES);
  consultar(`${BASE_URL}/api/leitores/${id}/emprestimos`, 'GET /api/leitores/{id}/emprestimos');
}

export function teardown() {
  laboratorio('DELETE', '/api/laboratorio/indices/leitor-data');
}

export function handleSummary(dados) {
  return resumir(dados, { cenario: 'indice', versao: VERSAO });
}

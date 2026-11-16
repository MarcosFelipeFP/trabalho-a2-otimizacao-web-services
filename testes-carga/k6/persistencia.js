// Cenário 2 (seção 6.2): a mesma página de empréstimos, cada um com o título do livro e o nome do
// leitor, buscada com estratégias de carregamento diferentes.
//
//   VERSAO       lazy | eager | otimizada | nativa
//                (a API também tem eager-selectin, eager-immediate e join-fetch)
//   QUANTIDADE   empréstimos por página (padrão 20)
//
// Cada requisição sorteia o primeiro id da página entre os 300.000 empréstimos.
//
// Exemplo: k6 run -e VERSAO=lazy -e CARGAS=50 testes-carga/k6/persistencia.js
import {
  BASE_URL, concluirPreparo, consultar, idAleatorio, montarOpcoes, resumir,
} from './comum.js';

const VERSOES = [
  'lazy', 'eager', 'eager-selectin', 'eager-immediate', 'join-fetch', 'otimizada', 'nativa',
];
const VERSAO = __ENV.VERSAO || 'lazy';
if (!VERSOES.includes(VERSAO)) {
  throw new Error(`VERSAO deve ser uma destas: ${VERSOES.join(', ')}`);
}
const QUANTIDADE = Number(__ENV.QUANTIDADE || 20);
const TOTAL_EMPRESTIMOS = Number(__ENV.TOTAL_EMPRESTIMOS || 300000);

export const options = montarOpcoes({ exec: 'listar' });

export function setup() {
  return concluirPreparo({ quantidade_por_pagina: QUANTIDADE });
}

export function listar() {
  const desde = idAleatorio(TOTAL_EMPRESTIMOS - QUANTIDADE);
  consultar(
    `${BASE_URL}/api/emprestimos/${VERSAO}?desde_id=${desde}&quantidade=${QUANTIDADE}`,
    `GET /api/emprestimos/${VERSAO}`,
  );
}

export function handleSummary(dados) {
  return resumir(dados, {
    cenario: 'persistencia', versao: VERSAO, extra: { quantidade_por_pagina: QUANTIDADE },
  });
}

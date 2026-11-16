// Opções e funções comuns aos cenários de teste de carga (Grafana k6).
//
// Uma execução do k6 percorre vários níveis de carga (CARGAS), um depois do outro. Em cada nível há
// um aquecimento, descartado, e depois a medição, com o mesmo número de usuários virtuais (VUs).
// Cada VU manda a próxima requisição assim que recebe a resposta: o número de VUs é a quantidade
// de requisições simultâneas, não a quantidade de requisições por segundo (seção 6.3).
//
// Variáveis de ambiente (k6 run -e NOME=valor):
//   BASE_URL      endereço da API                        padrão http://localhost:8000
//   CARGAS        níveis de carga, em VUs                padrão 10,50,100,200
//   AQUECIMENTO   segundos de aquecimento por nível      padrão 10
//   DURACAO       segundos de medição por nível          padrão 30
//   SAIDA         arquivo para gravar o resumo em JSON   opcional
//   SLO_P95_MS, SLO_P99_MS, SLO_ERROS: limites conferidos pelo k6 (padrão 500 ms, 1000 ms, 1%)
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

export const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const CARGAS = (__ENV.CARGAS || '10,50,100,200')
  .split(',')
  .map((v) => Number(v.trim()))
  .filter((v) => v > 0);
export const AQUECIMENTO = Number(__ENV.AQUECIMENTO ?? 10);
export const DURACAO = Number(__ENV.DURACAO || 30);
const INTERVALO = 3; // segundos de folga entre um nível e o seguinte

const LIMITES = {
  p95: Number(__ENV.SLO_P95_MS || 500),
  p99: Number(__ENV.SLO_P99_MS || 1000),
  erros: Number(__ENV.SLO_ERROS || 0.01),
};

// Métricas próprias, lidas dos cabeçalhos que a API devolve em toda resposta.
const consultasSql = new Trend('consultas_sql'); //            X-Consultas-SQL
const tempoNoBanco = new Trend('tempo_no_banco', true); //     Server-Timing: banco;dur=
const tempoNoServidor = new Trend('tempo_no_servidor', true); // Server-Timing: total;dur=
const acertosDoCache = new Rate('acertos_do_cache'); //        X-Cache: HIT ou MISS

// Início e fim de cada medição, em segundos contados do início dos cenários (como no k6).
const janelas = [];

// Monta os cenários do k6: para cada nível de carga, aquecimento -> (preparo) -> medição.
// "preparo" é uma função que roda uma vez antes de cada medição (ex.: esvaziar o cache).
export function montarOpcoes({ exec, preparo = null, cache = false }) {
  const scenarios = {};
  const thresholds = {};
  janelas.length = 0;
  let t = 0;
  for (const vus of CARGAS) {
    const carga = String(vus);
    if (AQUECIMENTO > 0) {
      scenarios[`aquecimento_${vus}vus`] = {
        executor: 'constant-vus', exec, vus, duration: `${AQUECIMENTO}s`, startTime: `${t}s`,
        gracefulStop: '2s', tags: { fase: 'aquecimento', carga },
      };
      t += AQUECIMENTO;
    }
    if (preparo) {
      scenarios[`preparo_${vus}vus`] = {
        executor: 'per-vu-iterations', exec: preparo, vus: 1, iterations: 1,
        startTime: `${t + 2}s`, maxDuration: '10s', tags: { fase: 'preparo' },
      };
      t += 3;
    }
    scenarios[`medicao_${vus}vus`] = {
      executor: 'constant-vus', exec, vus, duration: `${DURACAO}s`, startTime: `${t}s`,
      gracefulStop: '2s', tags: { fase: 'medicao', carga },
    };
    janelas.push({ vus, inicio_s: t, fim_s: t + DURACAO });
    t += DURACAO + INTERVALO;

    // Limites (SLOs) de cada nível. Os limites "sempre verdadeiros" (max>=0) só servem para o
    // k6 calcular a métrica separada por nível e incluí-la no resumo.
    const nivel = `{fase:medicao,carga:${carga}}`;
    thresholds[`http_req_duration${nivel}`] = [`p(95)<${LIMITES.p95}`, `p(99)<${LIMITES.p99}`];
    thresholds[`http_req_failed${nivel}`] = [`rate<${LIMITES.erros}`];
    thresholds[`http_reqs${nivel}`] = ['count>0'];
    thresholds[`data_received${nivel}`] = ['count>=0'];
    thresholds[`consultas_sql${nivel}`] = ['max>=0'];
    thresholds[`tempo_no_banco${nivel}`] = ['max>=0'];
    thresholds[`tempo_no_servidor${nivel}`] = ['max>=0'];
    if (cache) {
      thresholds[`acertos_do_cache${nivel}`] = ['rate>=0'];
    }
  }
  // total de requisições ao endpoint testado, somando aquecimento e medição
  thresholds['http_reqs{tipo:cenario}'] = ['count>0'];

  return {
    scenarios,
    thresholds,
    discardResponseBodies: true, // o corpo não é usado; descartá-lo poupa o gerador de carga
    summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
    batchPerHost: 50,
    setupTimeout: '180s',
  };
}

export function idAleatorio(maximo) {
  return 1 + Math.floor(Math.random() * maximo);
}

function cabecalho(resposta, nome) {
  const alvo = nome.toLowerCase();
  for (const chave in resposta.headers) {
    if (chave.toLowerCase() === alvo) return resposta.headers[chave];
  }
  return undefined;
}

// Requisição ao endpoint testado, com o registro das métricas próprias.
export function consultar(url, nome) {
  const resposta = http.get(url, { tags: { name: nome, tipo: 'cenario' } });
  check(resposta, { 'status 200': (r) => r.status === 200 });

  const sql = cabecalho(resposta, 'X-Consultas-SQL');
  if (sql !== undefined) consultasSql.add(Number(sql));
  const tempos = cabecalho(resposta, 'Server-Timing') || '';
  const banco = /banco;dur=([\d.]+)/.exec(tempos);
  const total = /total;dur=([\d.]+)/.exec(tempos);
  if (banco) tempoNoBanco.add(Number(banco[1]));
  if (total) tempoNoServidor.add(Number(total[1]));
  const cache = cabecalho(resposta, 'X-Cache');
  if (cache !== undefined) acertosDoCache.add(cache === 'HIT');
  return resposta;
}

// Chamada às rotas de laboratório, que preparam o estado da API antes da medição.
export function laboratorio(metodo, caminho) {
  const resposta = http.request(metodo, `${BASE_URL}${caminho}`, null, {
    tags: { name: `laboratorio ${caminho}`, tipo: 'laboratorio' },
    responseType: 'text',
  });
  if (resposta.status >= 300) {
    throw new Error(`${metodo} ${caminho} respondeu ${resposta.status}: ${resposta.body}`);
  }
  return resposta.json();
}

// Fim comum do setup(): registra o estado do banco (volume de dados, índices, configuração) e
// zera os contadores do PostgreSQL, para medir só o que a carga provocar daqui em diante.
export function concluirPreparo(extra = {}) {
  const estado = laboratorio('GET', '/api/laboratorio/estado');
  laboratorio('DELETE', '/api/laboratorio/banco/estatisticas');
  return { ...extra, estado, inicio_dos_cenarios_ms: Date.now() };
}

// ---------------------------------------------------------------------------------------------
// Resumo do teste: métricas de cada nível de carga, em JSON (SAIDA) e numa tabela no terminal.

function submetrica(dados, nome, tags) {
  for (const [chave, metrica] of Object.entries(dados.metrics)) {
    const m = /^([a-z_]+)\{(.*)\}$/.exec(chave);
    if (!m || m[1] !== nome) continue;
    const encontradas = Object.fromEntries(
      m[2].split(',').map((par) => par.split(':').map((s) => s.trim())),
    );
    const iguais = Object.entries(tags).every(([k, v]) => encontradas[k] === v);
    if (iguais && Object.keys(encontradas).length === Object.keys(tags).length) return metrica;
  }
  return null;
}

function limitesRespeitados(...metricas) {
  const resultado = {};
  for (const metrica of metricas) {
    for (const [limite, situacao] of Object.entries((metrica && metrica.thresholds) || {})) {
      if (!/>=0$|count>0$/.test(limite)) resultado[limite] = situacao.ok;
    }
  }
  return resultado;
}

export function resumir(dados, { cenario, versao, extra = {} }) {
  const niveis = CARGAS.map((vus) => {
    const tags = { fase: 'medicao', carga: String(vus) };
    const duracao = submetrica(dados, 'http_req_duration', tags);
    const falhas = submetrica(dados, 'http_req_failed', tags);
    const v = (nome) => {
      const m = submetrica(dados, nome, tags);
      return m ? m.values : null;
    };
    const requisicoes = v('http_reqs') ? v('http_reqs').count : 0;
    const lat = duracao ? duracao.values : {};
    return {
      vus,
      requisicoes,
      vazao_rps: requisicoes / DURACAO,
      latencia_ms: {
        media: lat.avg, minima: lat.min, mediana: lat.med, maxima: lat.max,
        p90: lat['p(90)'], p95: lat['p(95)'], p99: lat['p(99)'],
      },
      taxa_de_erros: falhas ? falhas.values.rate : null,
      consultas_sql_por_requisicao: v('consultas_sql') ? v('consultas_sql').avg : null,
      tempo_no_banco_ms: v('tempo_no_banco') ? v('tempo_no_banco').avg : null,
      tempo_no_servidor_ms: v('tempo_no_servidor') ? v('tempo_no_servidor').avg : null,
      taxa_de_acerto_do_cache: v('acertos_do_cache') ? v('acertos_do_cache').rate : null,
      bytes_recebidos: v('data_received') ? v('data_received').count : null,
      limites: limitesRespeitados(duracao, falhas),
    };
  });

  const totalDoEndpoint = submetrica(dados, 'http_reqs', { tipo: 'cenario' });
  const resumo = {
    cenario,
    versao,
    ...extra,
    base_url: BASE_URL,
    aquecimento_s: AQUECIMENTO,
    duracao_s: DURACAO,
    requisicoes_ao_endpoint: totalDoEndpoint ? totalDoEndpoint.values.count : null,
    preparo: dados.setup_data || null,
    janelas,
    niveis,
  };

  const saida = { stdout: tabela(resumo) };
  if (__ENV.SAIDA) {
    saida[__ENV.SAIDA] = JSON.stringify(resumo, null, 2);
    saida[__ENV.SAIDA.replace(/\.json$/, '') + '.completo.json'] = JSON.stringify(dados);
  }
  return saida;
}

function fmt(valor, casas = 1) {
  return valor === null || valor === undefined || Number.isNaN(valor) ? '-' : valor.toFixed(casas);
}

function tabela(resumo) {
  const linhas = [
    '',
    `  ${resumo.cenario} / ${resumo.versao}  (aquecimento ${resumo.aquecimento_s}s, medição ${resumo.duracao_s}s por nível)`,
    '    VUs   req/s    média     p95     p99   erros  SQL/req  cache  limites',
  ];
  for (const n of resumo.niveis) {
    const limites = Object.values(n.limites);
    linhas.push(
      [
        String(n.vus).padStart(7),
        fmt(n.vazao_rps, 0).padStart(7),
        fmt(n.latencia_ms.media).padStart(8),
        fmt(n.latencia_ms.p95).padStart(7),
        fmt(n.latencia_ms.p99).padStart(7),
        `${fmt((n.taxa_de_erros || 0) * 100, 2)}%`.padStart(7),
        fmt(n.consultas_sql_por_requisicao, 1).padStart(8),
        (n.taxa_de_acerto_do_cache === null ? '-' : `${fmt(n.taxa_de_acerto_do_cache * 100, 0)}%`).padStart(6),
        limites.length && limites.every(Boolean) ? '   ok' : '   ESTOURADO',
      ].join(' '),
    );
  }
  return linhas.join('\n') + '\n\n';
}

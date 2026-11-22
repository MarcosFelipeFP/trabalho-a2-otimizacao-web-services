'use strict';
// Painel de demonstração do Trabalho A2. Chama as rotas da API e mostra, a cada resposta, os
// cabeçalhos de medição que ela devolve (X-Consultas-SQL, Server-Timing e X-Cache). Sem
// bibliotecas externas.

const $ = (id) => document.getElementById(id);
const fmt = (n, casas = 0) => Number(n).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const ms = (n) => (n === null || n === undefined || Number.isNaN(n) ? '—' : n < 10 ? `${fmt(n, 2)} ms` : `${fmt(n, 0)} ms`);
const seg = (n) => `${fmt(n / 1000, n < 10000 ? 2 : 1)} s`;
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const plural = (n, um, varios) => `${fmt(n)} ${n === 1 ? um : varios}`;
const razao = (a, b) => (b > 0 ? a / b : 0);
const fator = (x) => `${fmt(x, x < 10 ? 1 : 0)}×`;

// ------------------------------------------------------------------ requisições HTTP
// Toda chamada à API passa por aqui. A faixa do rodapé mostra a última, com os cabeçalhos de medição.
const http = { total: 0, linhas: [] };

function linhaHttp(r) {
  const partes = [
    `<span class="verbo v-${r.metodo.toLowerCase()}">${r.metodo}</span>`,
    `<code class="rota">${esc(r.caminho)}</code>`,
    `<span class="status ${r.ok ? '' : 'falha'}">${r.status || 'sem resposta'}</span>`,
  ];
  if (r.cache) partes.push(`<span class="cab">X-Cache: <b>${esc(r.cache)}</b></span>`);
  if (r.invalidado) partes.push(`<span class="cab">X-Cache-Invalidado: <b>${esc(r.invalidado)}</b></span>`);
  if (r.temConsultas) partes.push(`<span class="cab">X-Consultas-SQL: <b>${r.consultas}</b></span>`);
  if (r.total !== null) partes.push(`<span class="cab">Server-Timing: banco <b>${ms(r.banco)}</b> · total <b>${ms(r.total)}</b></span>`);
  partes.push(`<span class="ida">${ms(r.ms)} no navegador</span>`);
  return partes.join('');
}

function registrarHttp(html) {
  http.total += 1;
  http.linhas.unshift(html);
  if (http.linhas.length > 60) http.linhas.pop();
  $('http-ultima').innerHTML = html;
  $('http-contagem').textContent = fmt(http.total);
  if (!$('http-lista').hidden) desenharListaHttp();
}

function registrarLote(descricao, resumo) {
  registrarHttp(`<span class="verbo v-lote">LOTE</span><code class="rota">${esc(descricao)}</code><span class="cab">${resumo}</span>`);
}

function desenharListaHttp() {
  $('http-lista').innerHTML = http.linhas.map((l) => `<li>${l}</li>`).join('');
}

$('http-alternar').addEventListener('click', () => {
  const aberto = $('http-alternar').getAttribute('aria-expanded') === 'true';
  $('http-alternar').setAttribute('aria-expanded', String(!aberto));
  $('http-lista').hidden = aberto;
  if (!aberto) desenharListaHttp();
});

async function chamar(metodo, caminho, corpo, { registrar = true } = {}) {
  // no-store: o cache HTTP do navegador enfileira pedidos iguais simultâneos e distorceria os tempos
  const opcoes = { method: metodo, cache: 'no-store' };
  if (corpo !== undefined) {
    opcoes.headers = { 'Content-Type': 'application/json' };
    opcoes.body = JSON.stringify(corpo);
  }
  const inicio = performance.now();
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    if (registrar) {
      registrarHttp(linhaHttp({ metodo, caminho, ok: false, status: 0, ms: performance.now() - inicio, total: null }));
    }
    throw new Error('A API não respondeu. Confira se os contêineres estão no ar (docker compose ps).');
  }
  const tipo = resposta.headers.get('content-type') || '';
  const dados = tipo.includes('json') ? await resposta.json() : await resposta.text();
  const tempos = resposta.headers.get('server-timing') || '';
  const numero = (re) => { const m = re.exec(tempos); return m ? parseFloat(m[1]) : null; };
  const consultas = resposta.headers.get('x-consultas-sql');
  const r = {
    ok: resposta.ok,
    status: resposta.status,
    metodo,
    caminho,
    dados,
    ms: performance.now() - inicio,
    consultas: Number(consultas ?? 0),
    temConsultas: consultas !== null,
    banco: numero(/banco;dur=([\d.]+)/),
    total: numero(/total;dur=([\d.]+)/),
    cache: resposta.headers.get('x-cache'),
    invalidado: resposta.headers.get('x-cache-invalidado'),
  };
  if (registrar) registrarHttp(linhaHttp(r));
  return r;
}

function erroDa(r) {
  const d = r.dados && r.dados.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((e) => e.msg).join('; ');
  return `A API respondeu ${r.status}.`;
}

function avisar(texto, tipo = 'erro') {
  const el = document.createElement('div');
  el.className = `aviso-flutuante ${tipo}`;
  el.setAttribute('role', tipo === 'erro' ? 'alert' : 'status');
  el.textContent = texto;
  $('avisos').append(el);
  setTimeout(() => el.remove(), 7000);
}

let trabalhando = false;
async function ocupado(botao, tarefa) {
  if (trabalhando) return;
  trabalhando = true;
  const botoes = document.querySelectorAll('main button');
  botoes.forEach((b) => { b.disabled = true; });
  botao.classList.add('trabalhando');
  botao.setAttribute('aria-busy', 'true');
  try {
    await tarefa();
  } catch (erro) {
    avisar(erro.message);
  } finally {
    botao.classList.remove('trabalhando');
    botao.removeAttribute('aria-busy');
    botoes.forEach((b) => { b.disabled = false; });
    trabalhando = false;
  }
}

const aoClicar = (id, tarefa) => $(id).addEventListener('click', (e) => ocupado(e.currentTarget, tarefa));

// ------------------------------------------------------------------ navegação
const SECOES = {
  visao: 'Visão geral',
  cache: 'Cache',
  carregamento: 'LAZY × EAGER',
  indices: 'Índices',
  carga: 'Testes de carga',
  resultados: 'Resultados e conclusões',
};

function abrirSecao() {
  const pedida = location.hash.slice(1);
  const alvo = SECOES[pedida] ? pedida : 'visao';
  document.querySelectorAll('.secao').forEach((s) => { s.hidden = s.id !== alvo; });
  document.querySelectorAll('.sumario a').forEach((a) => {
    if (a.dataset.secao === alvo) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  document.title = `${SECOES[alvo]} · Biblioteca · Painel de demonstração`;
  window.scrollTo(0, 0);
  if (alvo === 'resultados') desenharResultados();
}
window.addEventListener('hashchange', abrirSecao);

// ------------------------------------------------------------------ estado da API
const config = { ttl: 600 };

async function carregarEstado() {
  try {
    const r = await chamar('GET', '/api/laboratorio/estado');
    if (!r.ok) throw new Error();
    const d = r.dados;
    config.ttl = d.configuracao.cache_ttl_segundos;
    const redis = d.versoes.redis; // null: o Redis não respondeu, e a API segue com o banco
    $('luz').className = 'luz no-ar';
    $('estado-titulo').textContent = 'API no ar';
    $('estado-lista').innerHTML = [
      ['Empréstimos', fmt(d.tabelas.emprestimo)],
      ['Livros', fmt(d.tabelas.livro)],
      ['Leitores', fmt(d.tabelas.leitor)],
      ['Banco', `PostgreSQL ${d.banco.versao}`],
      ['Cache', redis ? `Redis ${redis}` : 'Redis fora do ar'],
      ['TTL', `${d.configuracao.cache_ttl_segundos} s`],
    ].map(([a, b]) => `<dt>${a}</dt><dd>${esc(b)}</dd>`).join('');
    if (d.configuracao.cache_tempo_limite_s) $('queda-limite').textContent = `${fmt(d.configuracao.cache_tempo_limite_s, 1)} s`;
    document.querySelectorAll('[data-tabela]').forEach((el) => { el.textContent = fmt(d.tabelas[el.dataset.tabela]); });
    $('resumo-dados').innerHTML = `<span><strong>${esc(d.tamanho_do_banco)}</strong> nas cinco tabelas, com os índices</span>`
      + `<span><strong>${fmt(d.emprestimos_em_aberto)}</strong> empréstimos em aberto</span>`;
    $('arq-processos').textContent = `${d.configuracao.workers} processos × ${d.configuracao.conexoes_por_worker} conexões com o banco`;
    $('arq-redis').textContent = redis || 'fora do ar';
    $('arq-pg').textContent = d.banco.versao;
    $('arq-ttl').textContent = `fichas dos livros, TTL de ${d.configuracao.cache_ttl_segundos} s`;
  } catch {
    $('luz').className = 'luz fora';
    $('estado-titulo').textContent = 'A API não respondeu';
    $('estado-lista').innerHTML = '<dt>Rode</dt><dd><code>docker compose up -d</code></dd>';
  }
}

// ------------------------------------------------------------------ 1. cache
let contador = 0;

function livroAtual() {
  const id = Number($('livro').value);
  if (!Number.isInteger(id) || id < 1 || id > 20000) throw new Error('Informe um livro de 1 a 20.000.');
  return id;
}

const MARCA_POR_FORA = ' [alterado direto no banco]';

function guardarTituloOriginal(id, titulo) {
  if (titulo.endsWith(MARCA_POR_FORA)) return;
  const chave = `titulo-original-${id}`;
  try { if (!localStorage.getItem(chave)) localStorage.setItem(chave, titulo); } catch { /* sem armazenamento */ }
}

function tituloOriginal(id) {
  try { return localStorage.getItem(`titulo-original-${id}`); } catch { return null; }
}

function horaDe(iso) {
  const m = /T(\d{2}:\d{2}:\d{2})(\.\d{1,3})?/.exec(iso || '');
  return m ? m[1] + (m[2] || '') : '—';
}

function nomeCatalografico(nome) {
  const partes = nome.trim().split(/\s+/);
  if (partes.length < 2) return nome.toUpperCase();
  const sobrenome = partes.pop();
  return `${sobrenome.toUpperCase()}, ${partes.join(' ')}`;
}

function mostrarFicha(f, desatualizada = false) {
  $('ficha-chamada').innerHTML = `<span>Livro ${f.id}</span><span>${esc(f.categoria.nome)}</span>`;
  $('ficha-autor').textContent = nomeCatalografico(f.autor.nome);
  $('ficha-titulo').textContent = `${f.titulo} / ${f.autor.nome}. — ${f.editora}, ${f.ano_publicacao}.`;
  $('ficha-imprenta').textContent = `${f.paginas} p. — ISBN ${f.isbn}`;
  $('ficha-notas').textContent = `${plural(f.total_exemplares, 'exemplar', 'exemplares')} · `
    + `${plural(f.circulacao.total_emprestimos, 'empréstimo', 'empréstimos')}`;
  $('ficha-gerada').innerHTML = `Ficha montada às <mark>${horaDe(f.gerada_em)}</mark>`;
  document.querySelector('.ficha-papel').classList.toggle('desatualizada', desatualizada);
}

function carimbar(lista) {
  // o carimbo cai à direita das linhas curtas da ficha (paginação e notas), sem cobrir o título
  $('carimbos').style.top = `${Math.max(54, $('ficha-imprenta').offsetTop - 4)}px`;
  $('carimbos').innerHTML = lista.map((c, i) => `<div class="carimbo ${c.tipo}" style="--giro:${i ? 4 : -6}deg;--atraso:${i * 160}ms">`
    + `<span class="carimbo-palavra">${esc(c.palavra)}</span>`
    + `${c.linha ? `<span class="carimbo-linha">${esc(c.linha)}</span>` : ''}</div>`).join('');
}

function mostrarMedicao(r) {
  $('m-consultas').textContent = r.consultas;
  $('m-banco').textContent = ms(r.banco);
  $('m-total').textContent = ms(r.total);
}

function anotarHistorico(operacao, r, etiqueta, classe) {
  const corpo = $('historico-cache');
  corpo.querySelector('.vazio')?.remove();
  contador += 1;
  const titulo = r.dados && r.dados.titulo ? r.dados.titulo : '—';
  corpo.insertAdjacentHTML('beforeend', `<tr><td class="n">${contador}</td><td>${esc(operacao)}</td>`
    + `<td><span class="etiqueta ${classe}">${esc(etiqueta)}</span></td><td class="n">${r.consultas}</td>`
    + `<td class="n">${ms(r.banco)}</td><td class="n">${ms(r.total)}</td><td>${esc(titulo)}</td></tr>`);
}

// TTL: sincroniza com o Redis depois de cada operação e conta os segundos aqui, sem consultar a API
const ttl = { ate: 0, base: 600, confirmando: false, expirou: false, foraDoAr: false };

function redisForaDoAr() {
  ttl.ate = 0;
  ttl.foraDoAr = true;
  desenharTtl();
}

async function sincronizarTtl(id) {
  const r = await chamar('GET', `/api/laboratorio/cache/livros/${id}`, undefined, { registrar: false });
  if (!r.ok) { redisForaDoAr(); return; } // 503: o Redis não respondeu
  ttl.foraDoAr = false;
  const { dados } = r;
  config.ttl = dados.ttl_configurado_segundos;
  if (dados.no_cache && dados.ttl_restante_segundos !== null) {
    ttl.expirou = false;
    if (dados.ttl_restante_segundos > ttl.base) ttl.base = config.ttl;
    ttl.ate = Date.now() + dados.ttl_restante_segundos * 1000;
  } else {
    ttl.ate = 0;
  }
  desenharTtl();
}

function desenharTtl() {
  const barra = $('ttl-barra');
  if (ttl.foraDoAr) {
    $('m-ttl').textContent = 'Redis fora do ar';
    barra.style.width = '0%';
    $('ttl-nota').textContent = 'O Redis não está respondendo: as leituras com cache vêm do banco (INDISPONIVEL) até ele voltar.';
    return;
  }
  if (!ttl.ate) {
    $('m-ttl').textContent = ttl.expirou ? 'expirou' : 'fora do cache';
    barra.style.width = '0%';
    $('ttl-nota').textContent = ttl.expirou
      ? 'O TTL acabou e o Redis apagou a ficha. A próxima leitura com cache é MISS e traz a versão do banco.'
      : 'A ficha deste livro não está no cache: a próxima leitura com cache será MISS.';
    return;
  }
  const restante = (ttl.ate - Date.now()) / 1000;
  if (restante <= 0) {
    ttl.expirou = true;
    $('m-ttl').textContent = 'expirou';
    barra.style.width = '0%';
    $('ttl-nota').textContent = 'O TTL acabou e o Redis apagou a ficha. A próxima leitura com cache é MISS e traz a versão do banco.';
    if (!ttl.confirmando) {
      ttl.confirmando = true;
      setTimeout(async () => {
        try { await sincronizarTtl(livroAtual()); } catch { /* sem API ou livro inválido: tenta no próximo clique */ }
        ttl.confirmando = false;
      }, 1200);
    }
    return;
  }
  $('m-ttl').textContent = `${Math.ceil(restante)} s`;
  barra.style.width = `${Math.min(100, (restante / ttl.base) * 100)}%`;
  barra.classList.toggle('acabando', restante <= 10);
  $('ttl-nota').textContent = `Restam ${Math.ceil(restante)} de ${ttl.base} s. Até lá, as leituras com cache são HIT; `
    + 'depois o Redis apaga a ficha sozinho.';
}
setInterval(desenharTtl, 250);

// experimento obrigatório da seção 3.4
const exp = { livro: null, passos: {}, tituloPut: null, tituloPorFora: null };
const DICA_DO_PASSO = {};
document.querySelectorAll('#passos li').forEach((li) => { DICA_DO_PASSO[li.dataset.passo] = li.querySelector('.prova').innerHTML; });

function recomecarExperimento(id = null) {
  exp.livro = id;
  exp.passos = {};
  exp.tituloPut = null;
  exp.tituloPorFora = null;
  desenharPassos();
}

function marcar(chave, html) {
  if (exp.passos[chave]) return;
  exp.passos[chave] = html;
  desenharPassos();
}

function desenharPassos() {
  document.querySelectorAll('#passos li').forEach((li) => {
    const passo = li.dataset.passo;
    const prova = li.querySelector('.prova');
    if (passo !== '5') {
      li.classList.toggle('feito', Boolean(exp.passos[passo]));
      prova.innerHTML = exp.passos[passo] || DICA_DO_PASSO[passo];
      return;
    }
    const partes = ['5a', '5b', '5t', '5c'].filter((k) => exp.passos[k]).map((k) => `<span class="sub-prova">${exp.passos[k]}</span>`);
    li.classList.toggle('feito', Boolean(exp.passos['5c']));
    li.classList.toggle('andamento', !exp.passos['5c'] && partes.length > 0);
    prova.innerHTML = partes.length ? partes.join('') : DICA_DO_PASSO[passo];
  });
}

function avancarExperimento(r, id) {
  if (exp.livro !== id) recomecarExperimento(id);
  const f = r.dados;
  const hora = horaDe(f.gerada_em);
  if (r.cache === 'MISS') {
    if (!exp.passos[1]) {
      marcar('1', `<span class="ok">MISS</span> · ${plural(r.consultas, 'consulta', 'consultas')} · ${ms(r.total)} · ficha montada às ${hora}`);
    } else if (exp.passos[3] && !exp.passos[4] && f.titulo === exp.tituloPut) {
      marcar('4', `<span class="ok">MISS</span> · já com o título novo: “${esc(f.titulo)}”`);
    }
    if (exp.passos['5a'] && f.titulo === exp.tituloPorFora) {
      marcar('5c', `Depois do TTL: <span class="ok">MISS</span>, com o título do banco (ficha montada às ${hora})`);
    }
  } else if (r.cache === 'HIT') {
    if (exp.passos[1] && !exp.passos[2]) {
      marcar('2', `<span class="ok">HIT</span> · ${plural(r.consultas, 'consulta', 'consultas')} · ${ms(r.total)} · a mesma ficha, montada às ${hora}`);
    }
    if (exp.passos['5a'] && exp.tituloPorFora && f.titulo !== exp.tituloPorFora) {
      marcar('5b', '<span class="ruim">HIT com o título antigo</span>: o usuário recebe um dado que o banco já não tem');
    }
  }
}

// E se o Redis cair? (seção 3.6 do README): leitura e alteração com o Redis travado, e a volta dele
const queda = { livro: null, passos: {}, ruins: new Set(), tituloPendente: null, ate: 0 };
const DICA_DA_QUEDA = {};
document.querySelectorAll('#passos-queda li').forEach((li) => { DICA_DA_QUEDA[li.dataset.passo] = li.querySelector('.prova').innerHTML; });

function recomecarQueda(id = null) {
  queda.livro = id;
  queda.passos = {};
  queda.ruins.clear();
  queda.tituloPendente = null;
  desenharQueda();
}

function marcarQueda(chave, html, ruim = false) {
  if (queda.passos[chave] && !queda.ruins.has(chave)) return;
  queda.passos[chave] = html;
  if (ruim) queda.ruins.add(chave); else queda.ruins.delete(chave);
  desenharQueda();
}

function desenharQueda() {
  document.querySelectorAll('#passos-queda li').forEach((li) => {
    const passo = li.dataset.passo;
    li.classList.toggle('feito', Boolean(queda.passos[passo]) && !queda.ruins.has(passo));
    li.classList.toggle('andamento', queda.ruins.has(passo));
    li.querySelector('.prova').innerHTML = queda.passos[passo] || DICA_DA_QUEDA[passo];
  });
}

function avancarQueda(r, id) {
  if (queda.livro !== id) recomecarQueda(id);
  const f = r.dados;
  if (r.cache === 'INDISPONIVEL') {
    marcarQueda('q1', `<span class="ok">200</span> · <code>X-Cache: INDISPONIVEL</code> · ${plural(r.consultas, 'consulta', 'consultas')} `
      + `· ${ms(r.total)}: a ficha veio do banco`);
  } else if (queda.passos.q2 && queda.tituloPendente !== null) {
    if (f.titulo === queda.tituloPendente) {
      marcarQueda('q3', `<span class="ok">${esc(r.cache)}</span> com o título novo: a vigia apagou a ficha antiga antes de o cache voltar`);
    } else if (r.cache === 'HIT') {
      marcarQueda('q3', '<span class="ruim">HIT com o título antigo</span>: outro processo da API leu o Redis antes de a vigia '
        + 'apagar a ficha; o atraso é de até 1 s, e o TTL limita o pior caso', true);
    }
  }
}

function desenharRelogioDaQueda() {
  const el = $('queda-relogio');
  if (!queda.ate) return;
  const restante = (queda.ate - Date.now()) / 1000;
  if (restante > 0) {
    el.textContent = `Redis travado: faltam ${Math.ceil(restante)} s`;
  } else if (restante > -30) {
    el.textContent = 'O Redis voltou: em até 1 s a vigia percebe, faz as invalidações pendentes e devolve o cache. Leia com cache.';
  } else {
    queda.ate = 0;
    el.textContent = '';
  }
}
setInterval(desenharRelogioDaQueda, 250);

async function lerFicha(comCache) {
  const id = livroAtual();
  const r = await chamar('GET', `/api/livros/${id}/${comCache ? 'com-cache' : 'sem-cache'}`);
  if (!r.ok) throw new Error(erroDa(r));
  const f = r.dados;
  guardarTituloOriginal(id, f.titulo);
  const resumo = `${plural(r.consultas, 'consulta', 'consultas')} · ${ms(r.total)}`;
  if (!comCache) {
    mostrarFicha(f);
    carimbar([{ tipo: 'banco', palavra: 'Banco', linha: resumo }]);
    $('detalhe-cache').innerHTML = `<strong>Sem cache</strong>: a ficha foi montada agora, com ${plural(r.consultas, 'consulta', 'consultas')} ao banco. `
      + 'Esta rota nunca usa o Redis.';
    anotarHistorico('GET ficha sem cache', r, 'banco', 'banco');
  } else if (r.cache === 'INDISPONIVEL') {
    mostrarFicha(f);
    carimbar([{ tipo: 'indisponivel', palavra: 'Indisponível', linha: `veio do banco · ${resumo}` }]);
    $('detalhe-cache').innerHTML = '<strong>INDISPONIVEL</strong>: o Redis não respondeu, e a ficha veio do banco '
      + `(${plural(r.consultas, 'consulta', 'consultas')}), como na versão sem cache. A requisição não falhou: o cache é só um atalho.`;
    anotarHistorico('GET ficha com cache', r, 'INDISPONIVEL', 'indisponivel');
    avancarQueda(r, id);
    mostrarMedicao(r);
    redisForaDoAr(); // sem consultar o TTL: a rota de laboratório também depende do Redis
    return;
  } else {
    const hit = r.cache === 'HIT';
    const velha = hit && exp.livro === id && exp.tituloPorFora !== null && f.titulo !== exp.tituloPorFora;
    mostrarFicha(f, velha);
    const carimbos = [{ tipo: hit ? 'hit' : 'miss', palavra: r.cache, linha: resumo }];
    if (velha) carimbos.push({ tipo: 'alerta', palavra: 'Desatualizada', linha: 'o banco tem outro título' });
    carimbar(carimbos);
    if (velha) {
      $('detalhe-cache').innerHTML = '<strong>HIT com dado desatualizado</strong>: o título mudou direto no banco e nada avisou o cache. '
        + 'A ficha antiga continua sendo servida até o TTL acabar.';
    } else if (hit) {
      $('detalhe-cache').innerHTML = `<strong>HIT</strong>: veio do Redis, sem consultar o banco. É a mesma ficha montada às ${horaDe(f.gerada_em)}.`;
    } else {
      $('detalhe-cache').innerHTML = `<strong>MISS</strong>: a ficha não estava no cache. Foi montada a partir do banco `
        + `(${plural(r.consultas, 'consulta', 'consultas')}) e guardada no Redis por ${config.ttl} s.`;
    }
    anotarHistorico('GET ficha com cache', r, velha ? 'HIT desatualizada' : r.cache, velha ? 'alerta' : hit ? 'hit' : 'miss');
    avancarExperimento(r, id);
    avancarQueda(r, id);
  }
  mostrarMedicao(r);
  await sincronizarTtl(id);
}

async function alterarPelaApi(titulo, operacao) {
  const id = livroAtual();
  const r = await chamar('PUT', `/api/livros/${id}`, { titulo });
  if (!r.ok) throw new Error(erroDa(r));
  if (exp.livro !== id) recomecarExperimento(id);
  exp.tituloPorFora = null;
  mostrarFicha(r.dados);
  mostrarMedicao(r);
  const pendente = r.invalidado === 'pendente';
  carimbar([{ tipo: pendente ? 'indisponivel' : 'escrita', palavra: 'Alterado',
    linha: r.invalidado === 'sim' ? 'ficha apagada do cache' : pendente ? 'invalidação pendente' : 'não havia ficha no cache' }]);
  $('detalhe-cache').innerHTML = pendente
    ? `<strong>PUT</strong>: título alterado para “${esc(titulo)}”. O Redis não respondeu, então a ficha antiga ainda não foi apagada `
      + '(<code>X-Cache-Invalidado: pendente</code>). A alteração já vale no banco; a vigia apaga a ficha assim que o Redis voltar, '
      + 'antes de o cache voltar a ser usado.'
    : `<strong>PUT</strong>: título alterado para “${esc(titulo)}”. Depois do commit, a API apagou a ficha do `
      + `cache (<code>X-Cache-Invalidado: ${esc(r.invalidado)}</code>). A próxima leitura com cache busca a versão nova no banco.`;
  anotarHistorico(operacao, r, `invalidou: ${r.invalidado}`, pendente ? 'indisponivel' : 'escrita');
  if (pendente) {
    if (queda.livro !== id) recomecarQueda(id);
    queda.tituloPendente = titulo;
    marcarQueda('q2', `<span class="ok">PUT</span> · <code>X-Cache-Invalidado: pendente</code> · ${ms(r.total)}: a alteração vale; `
      + 'a ficha antiga será apagada quando o Redis voltar');
    redisForaDoAr();
    return;
  }
  if (operacao === 'PUT alterar título') {
    exp.tituloPut = titulo;
    marcar('3', `<span class="ok">PUT</span> · <code>X-Cache-Invalidado: ${esc(r.invalidado)}</code> · ${ms(r.total)}`);
  }
  await sincronizarTtl(id);
}

async function tituloAtualDoBanco(id) {
  const r = await chamar('GET', `/api/livros/${id}/sem-cache`, undefined, { registrar: false });
  if (!r.ok) throw new Error(erroDa(r));
  guardarTituloOriginal(id, r.dados.titulo);
  return r.dados.titulo;
}

aoClicar('btn-com-cache', () => lerFicha(true));
aoClicar('btn-sem-cache', () => lerFicha(false));

aoClicar('btn-alterar', async () => {
  const id = livroAtual();
  if (!tituloOriginal(id)) await tituloAtualDoBanco(id);
  await alterarPelaApi($('novo-titulo').value.trim() || 'Novo título', 'PUT alterar título');
});

aoClicar('btn-restaurar', async () => {
  const original = tituloOriginal(livroAtual());
  if (!original) throw new Error('O título original deste livro ainda não foi lido neste navegador.');
  await alterarPelaApi(original, 'PUT restaurar título');
});

aoClicar('btn-esvaziar', async () => {
  const r = await chamar('DELETE', '/api/laboratorio/cache');
  if (!r.ok) throw new Error(erroDa(r));
  carimbar([]);
  ttl.expirou = false;
  $('detalhe-cache').innerHTML = `<strong>Cache esvaziado</strong>: ${plural(r.dados.chaves_removidas, 'ficha removida', 'fichas removidas')}. `
    + 'A próxima leitura com cache será MISS.';
  anotarHistorico('DELETE esvaziar o cache', r, `${r.dados.chaves_removidas} removidas`, 'banco');
  await sincronizarTtl(livroAtual());
});

aoClicar('btn-por-fora', async () => {
  const id = livroAtual();
  const original = tituloOriginal(id) || await tituloAtualDoBanco(id);
  const novo = `${original}${MARCA_POR_FORA}`;
  const r = await chamar('PUT', `/api/laboratorio/banco/livros/${id}/titulo`, { titulo: novo });
  if (!r.ok) throw new Error(erroDa(r));
  if (exp.livro !== id) recomecarExperimento(id);
  exp.tituloPorFora = novo;
  carimbar([{ tipo: 'escrita', palavra: 'Alterado no banco', linha: 'o cache não foi avisado' }]);
  $('detalhe-cache').innerHTML = `<strong>UPDATE direto no banco</strong>, por fora da API: o título agora é “${esc(novo)}”. `
    + (r.dados.ficha_no_cache === null
      ? 'O Redis não respondeu, então não dá para saber se a ficha antiga está no cache.'
      : r.dados.ficha_no_cache
        ? `A ficha antiga continua no cache por mais ${r.dados.ttl_restante_segundos} s. Leia com cache para ver o que o usuário recebe.`
        : 'A ficha não estava no cache, então a próxima leitura já traz o título novo. Para ver o dado desatualizado, leia com cache antes de alterar.');
  anotarHistorico('UPDATE direto no banco', r, 'cache não avisado', 'escrita');
  marcar('5a', `<span class="ok">UPDATE</span> direto no banco: ${r.dados.ficha_no_cache ? 'a ficha antiga continua no cache' : 'a ficha não estava no cache'}`);
  await sincronizarTtl(id);
});

aoClicar('btn-encurtar', async () => {
  const id = livroAtual();
  const r = await chamar('PUT', `/api/laboratorio/cache/livros/${id}/ttl?segundos=15`);
  if (!r.ok) throw new Error(erroDa(r));
  ttl.base = 15;
  ttl.ate = Date.now() + r.dados.ttl_restante_segundos * 1000;
  desenharTtl();
  $('detalhe-cache').innerHTML = '<strong>TTL encurtado para 15 s</strong> (<code>EXPIRE</code> no Redis), para a expiração caber na demonstração. '
    + 'Quando chegar a zero, o Redis apaga a ficha e a próxima leitura com cache é MISS.';
  if (exp.livro !== id) recomecarExperimento(id);
  marcar('5t', 'TTL desta ficha encurtado para 15 s');
});

aoClicar('btn-recomecar', async () => recomecarExperimento(livroAtual()));

aoClicar('btn-travar', async () => {
  const id = livroAtual();
  const r = await chamar('POST', '/api/laboratorio/cache/pausar?segundos=15');
  if (!r.ok) throw new Error(erroDa(r));
  const segundos = r.dados.redis_travado_por_segundos;
  if (queda.livro !== id) recomecarQueda(id);
  queda.ate = Date.now() + segundos * 1000;
  desenharRelogioDaQueda();
  $('detalhe-cache').innerHTML = `<strong>Redis travado por ${segundos} s</strong> (<code>CLIENT PAUSE</code>): ele segura os comandos `
    + 'de todos os processos da API, com as fichas ainda na memória. Leia com cache e altere o título enquanto isso; quando ele voltar, leia de novo.';
  anotarHistorico('POST travar o Redis', r, `travado por ${segundos} s`, 'indisponivel');
});

aoClicar('btn-recomecar-queda', async () => recomecarQueda(livroAtual()));

aoClicar('btn-disponibilidade', async () => {
  const id = livroAtual();
  const r = await chamar('GET', `/api/livros/${id}/disponibilidade`);
  if (!r.ok) throw new Error(erroDa(r));
  const d = r.dados;
  $('disponibilidade').innerHTML = `Livro ${id}: <strong>${d.exemplares_disponiveis} de ${plural(d.total_exemplares, 'exemplar', 'exemplares')}</strong> `
    + `disponível agora · ${plural(r.consultas, 'consulta', 'consultas')} ao banco · ${ms(r.total)} no servidor · sem cabeçalho `
    + '<code>X-Cache</code>: esta rota não passa pelo cache.';
});

$('livro').addEventListener('change', () => {
  try {
    const id = livroAtual();
    recomecarExperimento(id);
    recomecarQueda(id);
    ttl.expirou = false;
    sincronizarTtl(id).catch(() => {});
  } catch { /* número inválido: avisado no próximo clique */ }
});

// ------------------------------------------------------------------ 2. LAZY x EAGER
const ESTRATEGIAS = [
  ['lazy', 'LAZY', 'lazy="select": livro e leitor buscados um a um ao montar a resposta'],
  ['eager', 'EAGER', 'lazy="joined": LEFT OUTER JOIN com livro e leitor, 178 colunas'],
  ['eager-selectin', 'EAGER com selectinload', 'consultas separadas: SELECT … IN para livros e leitores'],
  ['eager-immediate', 'EAGER com immediateload', 'busca cada livro e cada leitor logo depois da página'],
  ['join-fetch', 'JOIN FETCH (joinedload)', 'mapeamento LAZY; a consulta pede o JOIN'],
  ['otimizada', 'Otimizada (projeção)', 'JOIN trazendo só as 8 colunas da resposta'],
  ['nativa', 'SQL nativo', 'a mesma consulta da otimizada, escrita em SQL'],
];
const nomeDa = (chave) => ESTRATEGIAS.find(([c]) => c === chave)[1];

function marcas(n, quantidade) {
  const tipo = n === 1 ? 'uma' : n > quantidade ? 'nmais1' : 'poucas';
  const mostradas = Math.min(n, 120);
  return `<span class="marcas ${tipo}" role="img" aria-label="${plural(n, 'consulta', 'consultas')}">${'<i></i>'.repeat(mostradas)}`
    + `${n > mostradas ? `<span class="mais">+${n - mostradas}</span>` : ''}</span>`;
}

function desenharEstrategias() {
  $('tabela-estrategias').innerHTML = ESTRATEGIAS.map(([chave, nome, desc]) => `<tr id="linha-${chave}">`
    + `<td><strong>${esc(nome)}</strong><span class="desc">${esc(desc)}</span></td>`
    + '<td class="n">—</td><td></td><td class="n">—</td><td class="n">—</td>'
    + `<td><button class="botao discreto" data-sql="${chave}">Ver SQL</button></td></tr>`).join('');
  document.querySelectorAll('[data-sql]').forEach((b) => b.addEventListener('click', (e) => ocupado(e.currentTarget, () => verSql(b.dataset.sql))));
}

async function compararEstrategias() {
  const quantidade = Number($('quantidade').value);
  const resultados = {};
  desenharEstrategias();
  $('conclusao-estrategias').hidden = true;
  for (const [chave] of ESTRATEGIAS) {
    const linha = $(`linha-${chave}`);
    linha.classList.add('rodando');
    const r = await chamar('GET', `/api/emprestimos/${chave}?desde_id=1000&quantidade=${quantidade}`);
    linha.classList.remove('rodando');
    if (!r.ok) throw new Error(erroDa(r));
    resultados[chave] = r;
    linha.cells[1].textContent = fmt(r.consultas);
    linha.cells[2].innerHTML = marcas(r.consultas, quantidade);
    linha.cells[3].textContent = ms(r.banco);
    linha.cells[4].textContent = ms(r.total);
  }
  const melhor = Object.entries(resultados).reduce((a, b) => (b[1].total < a[1].total ? b : a))[0];
  $(`linha-${melhor}`).classList.add('melhor');
  const { lazy, otimizada } = resultados;
  $('conclusao-estrategias').innerHTML = `Com ${quantidade} empréstimos por página, o <strong>LAZY</strong> fez `
    + `${plural(lazy.consultas, 'consulta', 'consultas')} e levou ${ms(lazy.total)} no servidor; a <strong>otimizada</strong> fez `
    + `${plural(otimizada.consultas, 'consulta', 'consultas')} e levou ${ms(otimizada.total)}: <strong class="ganho">`
    + `${fator(razao(lazy.total, otimizada.total))} mais rápida</strong>, com o mesmo JSON. Declarar EAGER não garante uma consulta só: `
    + `o selectinload fez ${resultados['eager-selectin'].consultas} e o immediateload, ${resultados['eager-immediate'].consultas}.`;
  $('conclusao-estrategias').hidden = false;
}

const PALAVRAS_SQL = /\b(SELECT|FROM|LEFT OUTER JOIN|JOIN|ON|WHERE|ORDER BY|LIMIT|AND|IN|DESC|ASC)\b/g;

async function verSql(chave) {
  const r = await chamar('GET', `/api/laboratorio/sql/emprestimos/${chave}?desde_id=150000&quantidade=3`);
  if (!r.ok) throw new Error(erroDa(r));
  const d = r.dados;
  $('cartao-sql').hidden = false;
  $('titulo-sql').textContent = `SQL executado pela estratégia ${nomeDa(chave)}, para uma página de 3 empréstimos`;
  const colunas = [...new Set(d.comandos.map((c) => c.colunas))].join(', ');
  $('resumo-sql').innerHTML = `<strong>${plural(d.consultas, 'consulta', 'consultas')}</strong> · ${fmt(d.linhas_lidas_do_banco)} linhas e `
    + `${fmt(d.bytes_lidos_do_banco)} bytes lidos do banco · colunas por linha: <strong>${colunas}</strong> · resposta da API: `
    + `${fmt(d.bytes_da_resposta)} bytes (igual nas sete)`;
  $('lista-sql').innerHTML = d.comandos.map((c) => {
    const sql = c.sql.replace(/\s+/g, ' ').trim();
    const curto = sql.length > 320 ? `${sql.slice(0, 320)} …` : sql;
    return `<li><code>${esc(curto).replace(PALAVRAS_SQL, '<b>$1</b>')}</code><span class="info">${plural(c.linhas, 'linha', 'linhas')}, `
      + `${c.colunas} colunas, ${fmt(c.bytes)} bytes, ${ms(c.duracao_ms)}</span></li>`;
  }).join('');
  $('cartao-sql').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

aoClicar('btn-comparar', compararEstrategias);

// ------------------------------------------------------------------ 3. índices
const INDICE = 'idx_emprestimo_leitor_data';
const planos = { sem: null, com: null };

async function listarIndices() {
  const { dados } = await chamar('GET', '/api/laboratorio/indices', undefined, { registrar: false });
  $('lista-indices').innerHTML = dados.map((i) => `<span class="chip ${i.nome === INDICE ? 'novo' : ''}">${esc(i.nome)} `
    + `<small>${fmt(i.bytes / 1048576, 1)} MB</small></span>`).join('');
}

function destacarPlano(linhas) {
  return linhas.map((l) => esc(l)
    .replace(/(Parallel Seq Scan|Seq Scan|Rows Removed by Filter: \d+|Sort Key: [^\n]+|Sort Method[^\n]*)/g, '<span class="ruim">$1</span>')
    .replace(/((?:Bitmap )?Index(?: Only)? Scan (?:using|on) \w+|Execution Time: [\d.]+ ms)/g, '<span class="bom">$1</span>'))
    .join('\n');
}

function resumoDoPlano(d) {
  const nos = d.operacoes.filter((o) => o.tabela === 'emprestimo' || (o.indice && o.indice.includes('emprestimo')));
  const varredura = [...new Set(nos.map((o) => o.operacao))].join(' + ') || '—';
  const examinadas = nos.filter((o) => o.tabela === 'emprestimo')
    .reduce((s, o) => s + o.linhas + o.linhas_descartadas_pelo_filtro, 0);
  const raiz = d.operacoes[0];
  return {
    varredura,
    examinadas,
    blocos: (raiz.blocos_em_memoria || 0) + (raiz.blocos_do_disco || 0),
    tempo: d.tempo_de_execucao_ms,
    ordena: d.tem_ordenacao,
  };
}

const leitura = (rotulo, valor) => `<div class="leitura"><span class="rotulo">${rotulo}</span><span class="valor">${valor}</span></div>`;

async function explicar() {
  const leitor = Number($('leitor').value);
  const r = await chamar('GET', `/api/laboratorio/explain/historico?leitor_id=${leitor}`);
  if (!r.ok) throw new Error(erroDa(r));
  const d = r.dados;
  const existe = d.indices_existentes.includes(INDICE);
  const p = { ...resumoDoPlano(d), leitor };
  planos[existe ? 'com' : 'sem'] = p;
  const usados = d.indices_usados.length
    ? d.indices_usados.map((i) => `<span class="chip ${i === INDICE ? 'novo' : ''}">${esc(i)} `
      + `<small>${i === INDICE ? 'o do experimento' : 'já existia'}</small></span>`).join('')
    : 'nenhum';
  const inteiras = d.tabelas_lidas_por_inteiro.length ? ` · leu inteira: <code>${d.tabelas_lidas_por_inteiro.map(esc).join(', ')}</code>` : '';
  $(existe ? 'plano-com' : 'plano-sem').innerHTML = `<h2>${existe ? 'Com o índice' : 'Sem o índice'} `
    + `<span class="etiqueta ${d.tabelas_lidas_por_inteiro.length ? 'miss' : 'hit'}">${esc(p.varredura)}</span></h2>`
    + '<div class="leituras plano-leituras">'
    + leitura('Tempo de execução', ms(p.tempo))
    + leitura('Linhas de empréstimo examinadas', fmt(p.examinadas))
    + leitura('Blocos lidos (8 KB cada)', fmt(p.blocos))
    + leitura('Ordenação (Sort)', p.ordena ? 'sim' : 'não')
    + '</div>'
    + `<p class="detalhe">Leitor ${leitor} · índices usados: ${usados}${inteiras}</p>`
    + `<pre class="plano">${destacarPlano(d.plano)}</pre>`;
  desenharComparativo();
}

function desenharComparativo() {
  const { sem, com } = planos;
  if (!sem || !com) { $('comparativo-indice').innerHTML = ''; return; }
  const linhas = [
    ['Tempo de execução no banco', ms(sem.tempo), ms(com.tempo), razao(sem.tempo, com.tempo)],
    ['Linhas de empréstimo examinadas', fmt(sem.examinadas), fmt(com.examinadas), razao(sem.examinadas, com.examinadas)],
    ['Blocos lidos (8 KB cada)', fmt(sem.blocos), fmt(com.blocos), razao(sem.blocos, com.blocos)],
    ['Ordenação (Sort)', sem.ordena ? 'sim' : 'não', com.ordena ? 'sim' : 'não', null],
  ];
  const mesmo = sem.leitor === com.leitor ? `do leitor ${com.leitor}` : `dos leitores ${sem.leitor} (sem) e ${com.leitor} (com)`;
  $('comparativo-indice').innerHTML = `<div class="cartao comparativo"><p class="frase">No histórico ${mesmo}, o índice fez o banco examinar `
    + `<strong class="ganho">${fmt(com.examinadas)}</strong> linhas em vez de ${fmt(sem.examinadas)} e executar a consulta em `
    + `<strong class="ganho">${ms(com.tempo)}</strong> em vez de ${ms(sem.tempo)}.</p>`
    + '<div class="rolagem"><table><thead><tr><th>No plano de execução</th><th class="n">Sem o índice</th><th class="n">Com o índice</th>'
    + '<th class="n">Diferença</th></tr></thead><tbody>'
    + linhas.map(([nome, a, b, x]) => `<tr><td>${nome}</td><td class="n">${a}</td><td class="n">${b}</td>`
      + `<td class="n ganho">${x === null ? (a === 'sim' && b === 'não' ? 'Sort eliminado' : '—') : x > 1 ? `${fator(x)} menos` : '—'}</td></tr>`).join('')
    + '</tbody></table></div></div>';
}

async function mudarIndice(metodo) {
  const r = await chamar(metodo, '/api/laboratorio/indices/leitor-data');
  if (!r.ok) throw new Error(erroDa(r));
  await listarIndices();
}

aoClicar('btn-explain', explicar);
aoClicar('btn-criar-indice', () => mudarIndice('PUT'));
aoClicar('btn-remover-indice', () => mudarIndice('DELETE'));
aoClicar('btn-historico', async () => {
  const id = Number($('leitor').value);
  const r = await chamar('GET', `/api/leitores/${id}/emprestimos`);
  if (!r.ok) throw new Error(erroDa(r));
  $('resultado-historico').innerHTML = `Histórico do leitor ${id} pela API: <strong>${plural(r.dados.quantidade, 'empréstimo', 'empréstimos')}</strong>, `
    + `${plural(r.consultas, 'consulta', 'consultas')}, ${ms(r.banco)} no banco e ${ms(r.total)} no servidor. Quase tudo é a viagem até o banco `
    + '(~155 ms): numa requisição isolada o índice muda pouco; o ganho aparece sob carga, quando o banco fica ocupado.';
});

// ------------------------------------------------------------------ em volume (cache, LAZY x EAGER e índices)
// Muitas requisições seguidas, 6 ao mesmo tempo (como um navegador), com as métricas da seção 6.4.
const progresso = (id, rotulo) => (feitos, n) => { $(id).textContent = `${rotulo}: ${feitos} de ${n}…`; };

async function emLote(n, simultaneas, tarefa, aviso) {
  const resultados = new Array(n);
  let proximo = 0;
  let feitos = 0;
  const inicio = performance.now();
  async function trabalhador() {
    while (proximo < n) {
      const i = proximo++;
      const t0 = performance.now();
      try {
        resultados[i] = await tarefa(i);
      } catch {
        resultados[i] = { ok: false, ms: performance.now() - t0, consultas: 0 };
      }
      feitos += 1;
      if (aviso) aviso(feitos, n);
    }
  }
  await Promise.all(Array.from({ length: Math.min(simultaneas, n) }, trabalhador));
  return { resultados, totalMs: performance.now() - inicio };
}

function percentil(valores, q) {
  const v = [...valores].sort((a, b) => a - b);
  return v[Math.max(0, Math.ceil(q * v.length) - 1)];
}

function resumoLote(nome, lote, { latencia = (x) => x.ms, extra = '—', totalMs } = {}) {
  const r = lote.resultados;
  const certos = r.filter((x) => x.ok);
  const lat = certos.map(latencia);
  return {
    nome,
    n: r.length,
    totalMs: totalMs ?? lote.totalMs,
    media: lat.length ? lat.reduce((s, x) => s + x, 0) / lat.length : null,
    p95: lat.length ? percentil(lat, 0.95) : null,
    p99: lat.length ? percentil(lat, 0.99) : null,
    rps: r.length / (lote.totalMs / 1000),
    erros: (r.length - certos.length) / r.length,
    consultas: r.reduce((s, x) => s + (x.consultas || 0), 0),
    extra,
  };
}

function mostrarVolume(alvo, linhas, frase, rotulos = {}) {
  const t = {
    total: 'Tempo total', ritmo: 'Vazão', unidade: 'req/s', media: 'Latência média', consultas: 'Consultas SQL',
    ganho: 'Mais rápido que o pior', fmtTotal: seg,
    nota: 'Latências medidas no navegador, do envio da requisição ao fim da resposta, como o k6 mede.', ...rotulos,
  };
  const maior = Math.max(...linhas.map((l) => l.totalMs));
  const menor = Math.min(...linhas.map((l) => l.totalMs));
  const poucas = linhas[0].n < 20 ? ' Com tão poucas, p95 e p99 são o maior tempo medido.' : '';
  const quantas = ` ${plural(linhas[0].n, 'requisição', 'requisições')} por versão, 6 ao mesmo tempo.`;
  $(alvo).innerHTML = `<div class="cartao volume-resultado"><p class="frase">${frase}</p><div class="rolagem"><table><thead><tr>`
    + `<th>Versão</th><th class="col-barra">${t.total}</th><th class="n">${t.ritmo}</th>`
    + `<th class="n">${t.media}</th><th class="n">p95</th><th class="n">p99</th><th class="n">Erros</th><th class="n">${t.consultas}</th>`
    + `${t.extra ? `<th class="n">${t.extra}</th>` : ''}<th class="n">${t.ganho}</th></tr></thead><tbody>`
    + linhas.map((l) => `<tr class="${l.totalMs === menor ? 'melhor' : ''}"><td class="versao">${esc(l.nome)}</td>`
      + `<td class="col-barra"><span class="n">${t.fmtTotal(l.totalMs)}</span><div class="barra-tempo ${l.totalMs === menor ? 'melhor' : ''}" `
      + `style="width:${Math.max(1, (l.totalMs / maior) * 100)}%"></div></td>`
      + `<td class="n">${fmt(l.rps, 1)}${t.unidade ? ` ${t.unidade}` : ''}</td><td class="n">${ms(l.media)}</td><td class="n">${ms(l.p95)}</td><td class="n">${ms(l.p99)}</td>`
      + `<td class="n">${fmt(l.erros * 100, 0)}%</td><td class="n">${fmt(l.consultas)}</td>`
      + `${t.extra ? `<td class="n">${l.extra}</td>` : ''}`
      + `<td class="n ganho">${l.totalMs === maior ? '—' : fator(maior / l.totalMs)}</td></tr>`).join('')
    + `</tbody></table></div><p class="nota">${t.nota}${quantas}${poucas}</p></div>`;
}

aoClicar('btn-vol-cache', async () => {
  const n = Number($('vol-cache-n').value);
  const livros = Number($('vol-cache-livros').value);
  const id = (i) => 1000 + (i % livros) * 37; // livros fora da demonstração: o da ficha não é tocado
  const sozinho = { registrar: false };
  await chamar('DELETE', '/api/laboratorio/cache', undefined, sozinho);
  const sem = await emLote(n, 6, (i) => chamar('GET', `/api/livros/${id(i)}/sem-cache?r=${i}`, undefined, sozinho), progresso('prog-cache', 'Sem cache'));
  const com = await emLote(n, 6, (i) => chamar('GET', `/api/livros/${id(i)}/com-cache?r=${i}`, undefined, sozinho), progresso('prog-cache', 'Com cache'));
  await chamar('DELETE', '/api/laboratorio/cache', undefined, sozinho);
  const acertos = com.resultados.filter((r) => r.cache === 'HIT').length;
  const a = resumoLote('Sem cache', sem);
  const b = resumoLote('Com cache', com, { extra: `${acertos} de ${n}` });
  registrarLote(`${n} × GET /api/livros/{id}/sem-cache`, `${seg(a.totalMs)} · ${fmt(a.rps, 1)} req/s · ${fmt(a.consultas)} consultas SQL`);
  registrarLote(`${n} × GET /api/livros/{id}/com-cache`, `${seg(b.totalMs)} · ${fmt(b.rps, 1)} req/s · ${fmt(b.consultas)} consultas SQL · ${acertos} HIT`);
  $('prog-cache').textContent = 'Concluído. O cache foi esvaziado no fim, para não atrapalhar a demonstração.';
  mostrarVolume('vol-cache', [a, b], `${n} leituras de ${plural(livros, 'livro', 'livros')}, com o cache começando vazio: <strong class="ganho">${seg(b.totalMs)}</strong> `
    + `com cache contra ${seg(a.totalMs)} sem cache, <strong class="ganho">${fator(a.totalMs / b.totalMs)} mais rápido</strong>. `
    + `p95 de ${ms(b.p95)} contra ${ms(a.p95)}, e ${fmt(a.consultas - b.consultas)} consultas a menos ao banco.`,
  { extra: 'Acertos no cache' });
});

aoClicar('btn-vol-emp', async () => {
  const n = Number($('vol-emp-n').value);
  const q = Number($('vol-emp-q').value);
  const escolhidas = q <= 20 ? ['lazy', 'eager', 'otimizada'] : ['eager', 'join-fetch', 'otimizada', 'nativa'];
  const sozinho = { registrar: false };
  const linhas = [];
  for (const chave of escolhidas) {
    const nome = nomeDa(chave);
    if (chave !== 'lazy') await chamar('GET', `/api/emprestimos/${chave}?desde_id=900&quantidade=${q}`, undefined, sozinho); // aquecimento
    const lote = await emLote(n, 6, (i) => chamar('GET', `/api/emprestimos/${chave}?desde_id=${1000 + i * q}&quantidade=${q}`, undefined, sozinho),
      progresso('prog-emp', nome));
    let lido = '—';
    if (chave !== 'lazy') {
      const { dados } = await chamar('GET', `/api/laboratorio/sql/emprestimos/${chave}?desde_id=1000&quantidade=${q}`, undefined, sozinho);
      lido = `${fmt(dados.bytes_lidos_do_banco / 1024, 1)} KB`;
    }
    const resumo = resumoLote(nome, lote, { extra: lido });
    resumo.chave = chave;
    registrarLote(`${n} × GET /api/emprestimos/${chave}?quantidade=${q}`, `${seg(resumo.totalMs)} · ${fmt(resumo.rps, 1)} req/s · ${fmt(resumo.consultas)} consultas SQL`);
    linhas.push(resumo);
  }
  $('prog-emp').textContent = 'Concluído.';
  const pior = linhas.reduce((x, y) => (x.totalMs > y.totalMs ? x : y));
  const melhor = linhas.reduce((x, y) => (x.totalMs < y.totalMs ? x : y));
  let frase = `${n} páginas de ${q} empréstimos: <strong>${esc(melhor.nome)}</strong> em <strong class="ganho">`
    + `${seg(melhor.totalMs)}</strong> contra ${seg(pior.totalMs)} do ${esc(pior.nome)}, <strong class="ganho">${fator(pior.totalMs / melhor.totalMs)} `
    + `mais rápido</strong>. p95 de ${ms(melhor.p95)} contra ${ms(pior.p95)}.`;
  if (q > 20) {
    // com páginas grandes, o que importa é o custo das 178 colunas: EAGER contra a projeção
    const de = (c) => linhas.find((l) => l.chave === c);
    const eager = de('eager');
    const otim = de('otimizada');
    const x = eager.totalMs / otim.totalMs;
    frase = `${n} páginas de ${q} empréstimos: o <strong>EAGER</strong> leu <strong>${eager.extra}</strong> do banco por página, com as 178 colunas, `
      + `e a <strong>otimizada</strong>, <strong class="ganho">${otim.extra}</strong>; tempo total de ${seg(eager.totalMs)} contra `
      + `${seg(otim.totalMs)}${x >= 1.05 ? `, <strong class="ganho">${fator(x)} mais rápida</strong>` : ', sem diferença de tempo nesta rodada'}. `
      + 'O SQL nativo executa a mesma consulta da otimizada e lê os mesmos bytes: a diferença de tempo entre os dois muda de uma rodada para outra.';
  }
  mostrarVolume('vol-emp', linhas, frase, { extra: 'Lido por página' });
});

aoClicar('btn-vol-idx', async () => {
  const n = Number($('vol-idx-n').value);
  const leitor = (i) => 1 + ((i * 197) % 10000);
  const sozinho = { registrar: false };
  const antes = (await chamar('GET', '/api/laboratorio/indices', undefined, sozinho)).dados.some((i) => i.nome === INDICE);
  const rodada = async (nome) => {
    const lote = await emLote(n, 6, (i) => chamar('GET', `/api/laboratorio/explain/historico?leitor_id=${leitor(i)}`, undefined, sozinho),
      progresso('prog-idx', nome));
    const certos = lote.resultados.filter((r) => r.ok);
    const banco = certos.reduce((s, r) => s + r.dados.tempo_de_execucao_ms, 0);
    const varreduras = certos.filter((r) => r.dados.tabelas_lidas_por_inteiro.length).length;
    const resumo = resumoLote(nome, lote, { latencia: (x) => x.dados.tempo_de_execucao_ms, extra: `${varreduras} de ${n}`, totalMs: banco });
    resumo.varreduras = varreduras;
    resumo.consultas = certos.length;
    registrarLote(`${n} × GET /api/laboratorio/explain/historico`, `${nome}: ${ms(banco)} de execução no banco, somados`);
    return resumo;
  };
  await chamar('DELETE', '/api/laboratorio/indices/leitor-data', undefined, sozinho);
  const sem = await rodada('Sem índice');
  await chamar('PUT', '/api/laboratorio/indices/leitor-data', undefined, sozinho);
  const com = await rodada('Com o índice');
  if (!antes) await chamar('DELETE', '/api/laboratorio/indices/leitor-data', undefined, sozinho);
  await listarIndices();
  $('prog-idx').textContent = antes ? 'Concluído.' : 'Concluído. O índice foi removido no fim, como estava antes.';
  mostrarVolume('vol-idx', [sem, com], `${n} leitores: o banco trabalhou <strong class="ganho">${ms(com.totalMs)}</strong> com o índice `
    + `contra ${ms(sem.totalMs)} sem ele, <strong class="ganho">${fmt(sem.totalMs / com.totalMs, 0)}× menos trabalho</strong>. `
    + `Sem o índice, ${sem.varreduras} de ${n} consultas leram a tabela inteira (Seq Scan).`,
  {
    total: 'Execução somada no banco', ritmo: 'EXPLAIN/s', unidade: '', media: 'Execução média', consultas: 'Consultas analisadas',
    ganho: 'Menos trabalho', fmtTotal: ms,
    extra: 'Seq Scan', nota: 'Tempos de execução no banco, do EXPLAIN ANALYZE de cada consulta; a viagem até o banco fica de fora.',
  });
});

// ------------------------------------------------------------------ 4. testes de carga
const CENARIOS_K6 = {
  cache: {
    comando: 'k6 run k6/cache.js -e VERSAO=com-cache-quente -e CARGAS=50',
    nota: 'Cenário 1. Antes de medir, o script guarda no cache as fichas dos 20.000 livros (cache quente).',
    depois: 'O cache fica cheio. Para repetir a demonstração do cache, use “Esvaziar o cache” na seção Cache.',
  },
  persistencia: {
    comando: 'k6 run k6/persistencia.js -e VERSAO=otimizada -e CARGAS=50',
    nota: 'Cenário 2. Cada requisição pede uma página de 20 empréstimos a partir de um id sorteado.',
    depois: 'Nada a desfazer: o teste só lê.',
  },
  indice: {
    comando: 'k6 run k6/indice.js -e VERSAO=com-indice -e CARGAS=50',
    nota: 'Cenário 3. O script cria o índice antes de medir.',
    depois: 'Nada a desfazer: o script remove o índice no fim.',
  },
};

function escolherNoGrupo(grupo, botao) {
  grupo.querySelectorAll('[role="radio"]').forEach((b) => b.setAttribute('aria-checked', String(b === botao)));
}

function selecionarCenarioK6(chave) {
  const c = CENARIOS_K6[chave];
  $('comando-k6').textContent = `docker compose run --rm --service-ports -e K6_WEB_DASHBOARD=true ${c.comando}`;
  $('cenario-nota').textContent = c.nota;
  $('cenario-depois').textContent = c.depois;
  $('copiado').textContent = '';
}

$('cenario-k6').addEventListener('click', (e) => {
  const botao = e.target.closest('[data-cenario]');
  if (!botao) return;
  escolherNoGrupo($('cenario-k6'), botao);
  selecionarCenarioK6(botao.dataset.cenario);
});

$('btn-copiar').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('comando-k6').textContent);
    $('copiado').textContent = 'Copiado. Cole no terminal aberto na pasta do projeto.';
  } catch {
    $('copiado').textContent = 'Selecione o comando e copie com Ctrl+C.';
  }
});

// ------------------------------------------------------------------ 5. resultados da matriz do k6
// Médias de 3 repetições (README, seção 5.3). Cada linha: [vazão req/s, média ms, p95 ms, p99 ms, SQL por req.]
const RESULTADOS = {
  cache: {
    titulo: 'Cenário 1 · ficha do livro sem e com cache',
    versoes: ['sem cache', 'cache frio', 'cache quente'],
    cores: ['var(--serie-1)', 'var(--serie-2)', 'var(--serie-3)'],
    destaque: 2,
    dados: {
      10: [[18, 577, 771, 1348, 3.0], [18, 578, 936, 1116, 2.7], [4626, 2.12, 4.51, 6.79, 0.0]],
      50: [[25.4, 2009, 2888, 5433, 3.0], [30.6, 1662, 3611, 3638, 2.6], [5713, 8.60, 18.5, 28.9, 0.0]],
      100: [[24, 3904, 10638, 16782, 3.0], [30, 3268, 6570, 6659, 2.6], [5700, 17.4, 36.2, 53.5, 0.0]],
      200: [[18, 8764, 19313, 25153, 3.0], [27, 6866, 13558, 17881, 2.6], [5746, 34.6, 66.2, 102, 0.0]],
    },
    nota: 'Cache frio: esvaziado antes de cada nível; em 30 s só os livros mais procurados se repetem, e a taxa de acerto ficou entre 9% e 14%.',
  },
  persistencia: {
    titulo: 'Cenário 2 · página de 20 empréstimos com livro e leitor',
    versoes: ['LAZY', 'EAGER', 'otimizada', 'SQL nativo'],
    cores: ['var(--serie-1)', 'var(--serie-2)', 'var(--serie-3)', 'var(--serie-4)'],
    destaque: 2,
    dados: {
      10: [[0.8, 10714, 19156, 21092, 40.9], [45, 230, 320, 381, 1.0], [58, 172, 225, 281, 1.0], [48, 218, 305, 381, 1.0]],
      50: [[0.8, 22453, 29729, 30050, 41.0], [75.0, 674, 808, 1217, 1.0], [76.8, 659, 922, 1140, 1.0], [71.1, 725, 1115, 1309, 1.0]],
      100: [[0.2, 18353, 27627, 28617, 41.0], [74, 1379, 2802, 4624, 1.0], [77, 1335, 3476, 5059, 1.0], [77, 1320, 3299, 4928, 1.0]],
      200: [[0.0, null, null, null, null], [73, 2746, 5613, 8336, 1.0], [75, 2698, 5957, 8695, 1.0], [76, 2671, 6417, 8810, 1.0]],
    },
    nota: 'LAZY: só as requisições que terminaram dentro da janela de 30 s; com 200 VUs, nenhuma terminou.',
  },
  indice: {
    titulo: 'Cenário 3 · histórico de empréstimos de um leitor, sem e com índice',
    versoes: ['sem índice', 'com índice'],
    cores: ['var(--serie-1)', 'var(--serie-3)'],
    destaque: 1,
    dados: {
      10: [[35, 321, 439, 669, 1.0], [54, 188, 254, 302, 1.0]],
      50: [[48.5, 1059, 2220, 2479, 1.0], [76.7, 659, 765, 1118, 1.0]],
      100: [[52, 1964, 4857, 7256, 1.0], [66, 1543, 4922, 7051, 1.0]],
      200: [[49, 4030, 9367, 13085, 1.0], [75, 2683, 6228, 9002, 1.0]],
    },
    nota: 'Com 100 VUs, uma das repetições pegou o banco mais lento (a instância do Supabase tem CPU compartilhada), daí a vazão menor com o índice nesse nível.',
  },
};
const NIVEIS = [10, 50, 100, 200];
const METRICAS = {
  vazao: { i: 0, nome: 'Vazão (req/s)', unidade: 'req/s' },
  media: { i: 1, nome: 'Latência média (ms)', unidade: 'ms' },
  p95: { i: 2, nome: 'Latência p95 (ms)', unidade: 'ms' },
  p99: { i: 3, nome: 'Latência p99 (ms)', unidade: 'ms' },
};
const filtro = { cenario: 'cache', metrica: 'vazao' };

const fmtVazao = (v) => (v < 1 || !Number.isInteger(v) ? fmt(v, 1) : fmt(v));
const fmtMs = (v) => fmt(v, v < 10 ? 2 : v < 100 ? 1 : 0);
const fmtValor = (v, metrica) => (metrica === 'vazao' ? fmtVazao(v) : fmtMs(v));

function escalaBonita(maximo) {
  if (!(maximo > 0)) return { max: 1, ticks: [0, 1] };
  const bruto = maximo / 4;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((p) => p * potencia).find((p) => p >= bruto);
  const max = Math.ceil(maximo / passo - 1e-9) * passo;
  const ticks = [];
  for (let t = 0; t <= max + passo / 2; t += passo) ticks.push(Number(t.toFixed(6)));
  return { max, ticks };
}

const rotuloEixo = (t, max) => (max >= 10000 && t >= 1000 ? `${fmt(t / 1000, t % 1000 ? 1 : 0)} mil` : fmt(t, t < 10 && t % 1 ? 1 : 0));

function caminhoBarra(x, y, w, h) {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function desenharGrafico() {
  const c = RESULTADOS[filtro.cenario];
  const m = METRICAS[filtro.metrica];
  const el = $('grafico');
  const largura = Math.max(320, el.clientWidth);
  const altura = el.clientHeight || 310;
  const mg = { topo: 26, direita: 8, base: 34, esquerda: 62 };
  const w = largura - mg.esquerda - mg.direita;
  const h = altura - mg.topo - mg.base;
  const valores = NIVEIS.flatMap((v) => c.dados[v].map((linha) => linha[m.i])).filter((x) => x !== null);
  const escala = escalaBonita(Math.max(...valores));
  const y = (v) => mg.topo + h - (v / escala.max) * h;
  const banda = w / NIVEIS.length;
  const n = c.versoes.length;
  const larg = Math.min(24, (banda * 0.62 - (n - 1) * 2) / n);
  const grupo = n * larg + (n - 1) * 2;
  const base = mg.topo + h;
  let svg = `<svg viewBox="0 0 ${largura} ${altura}" role="img" aria-label="${esc(`${m.nome} por nível de carga, ${c.titulo}`)}">`;
  escala.ticks.forEach((t) => {
    svg += `<line class="${t === 0 ? 'base' : 'grade'}" x1="${mg.esquerda}" x2="${largura - mg.direita}" y1="${y(t)}" y2="${y(t)}"/>`
      + `<text x="${mg.esquerda - 8}" y="${y(t) + 4}" text-anchor="end">${rotuloEixo(t, escala.max)}</text>`;
  });
  NIVEIS.forEach((vus, gi) => {
    const x0 = mg.esquerda + gi * banda + (banda - grupo) / 2;
    const linhas = c.dados[vus];
    const topoDoGrupo = Math.min(...linhas.map((l) => (l[m.i] === null ? base : y(l[m.i]))));
    linhas.forEach((linha, si) => {
      const v = linha[m.i];
      const x = x0 + si * (larg + 2);
      if (v === null) {
        svg += `<text x="${x + larg / 2}" y="${base - 6}" text-anchor="middle">–</text>`;
        return;
      }
      const alturaBarra = Math.max(v > 0 ? 1 : 0, base - y(v));
      const dica = `${vus} VUs · ${c.versoes[si]}: ${fmtValor(v, filtro.metrica)} ${m.unidade}`;
      svg += `<path class="barra-svg" d="${caminhoBarra(x, base - alturaBarra, larg, alturaBarra)}" style="fill:${c.cores[si]}" data-dica="${esc(dica)}"/>`;
      if (si === c.destaque) {
        const yRotulo = Math.min(base - alturaBarra, topoDoGrupo) - 8;
        if (base - alturaBarra - yRotulo > 14) {
          svg += `<line class="guia" x1="${x + larg / 2}" x2="${x + larg / 2}" y1="${yRotulo + 4}" y2="${base - alturaBarra - 2}"/>`;
        }
        svg += `<text class="rotulo-valor" x="${x + larg / 2}" y="${yRotulo}" text-anchor="middle">${fmtValor(v, filtro.metrica)}</text>`;
      }
    });
    svg += `<text x="${mg.esquerda + gi * banda + banda / 2}" y="${altura - 10}" text-anchor="middle">${vus} VUs</text>`;
  });
  el.innerHTML = `${svg}</svg>`;
}

function desenharResultados() {
  const c = RESULTADOS[filtro.cenario];
  const m = METRICAS[filtro.metrica];
  $('grafico-titulo').textContent = `${m.nome} com 10, 50, 100 e 200 usuários virtuais · ${c.titulo}`;
  $('grafico-legenda').innerHTML = c.versoes.map((v, i) => `<li><i style="background:${c.cores[i]}"></i>${esc(v)}</li>`).join('');
  const valores = NIVEIS.flatMap((v) => c.dados[v].map((l) => l[m.i])).filter((x) => x > 0);
  const rentes = valores.some((x) => x < Math.max(...valores) / 100)
    ? 'Na escala linear, as barras com menos de 1% da maior ficam rentes ao eixo; os valores estão na tabela. ' : '';
  $('grafico-nota').textContent = `${c.nota} ${rentes}O número escrito é o da versão ${c.versoes[c.destaque]}; `
    + 'passe o mouse sobre as barras para ver as outras.';
  desenharGrafico();
  $('tabela-resultados').innerHTML = NIVEIS.map((vus) => c.dados[vus].map((l, si) => {
    const semDado = l[1] === null;
    return `<tr class="${si === c.destaque ? 'melhor' : ''}"><td class="n">${vus}</td>`
      + `<td><i class="amostra" style="background:${c.cores[si]}"></i>${esc(c.versoes[si])}</td>`
      + `<td class="n">${fmtVazao(l[0])} req/s</td>`
      + `<td class="n">${semDado ? '–' : `${fmtMs(l[1])} ms`}</td><td class="n">${semDado ? '–' : `${fmtMs(l[2])} ms`}</td>`
      + `<td class="n">${semDado ? '–' : `${fmtMs(l[3])} ms`}</td><td class="n">${semDado ? '–' : '0%'}</td>`
      + `<td class="n">${semDado ? '–' : fmt(l[4], 1)}</td></tr>`;
  }).join('')).join('');
}

['filtro-cenario', 'filtro-metrica'].forEach((id) => $(id).addEventListener('click', (e) => {
  const botao = e.target.closest('[data-valor]');
  if (!botao) return;
  escolherNoGrupo($(id), botao);
  filtro[id === 'filtro-cenario' ? 'cenario' : 'metrica'] = botao.dataset.valor;
  desenharResultados();
}));

const dica = $('dica');
$('grafico').addEventListener('pointermove', (e) => {
  const alvo = e.target.closest('[data-dica]');
  if (!alvo) { dica.hidden = true; return; }
  dica.textContent = alvo.dataset.dica;
  dica.hidden = false;
  dica.style.left = `${Math.min(e.clientX + 14, window.innerWidth - dica.offsetWidth - 8)}px`;
  dica.style.top = `${e.clientY - 38}px`;
});
$('grafico').addEventListener('pointerleave', () => { dica.hidden = true; });
new ResizeObserver(() => { if (!$('resultados').hidden) desenharGrafico(); }).observe($('grafico'));

// ------------------------------------------------------------------ início
desenharEstrategias();
desenharPassos();
selecionarCenarioK6('cache');
abrirSecao();
carregarEstado();
listarIndices().catch(() => {});

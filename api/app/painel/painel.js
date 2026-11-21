// Painel de demonstração: chama as rotas da API e mostra, para cada resposta, os números que a
// API devolve nos cabeçalhos (X-Consultas-SQL, Server-Timing, X-Cache). Sem bibliotecas externas.

const $ = (id) => document.getElementById(id);
const fmt = (n, casas = 0) => Number(n).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
const ms = (n) => (n === null || Number.isNaN(n) ? '—' : n < 10 ? `${fmt(n, 2)} ms` : `${fmt(n, 0)} ms`);
const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

async function chamar(metodo, caminho, corpo) {
  // no-store: o cache HTTP do navegador enfileira pedidos iguais simultâneos e distorceria os tempos
  const opcoes = { method: metodo, cache: 'no-store' };
  if (corpo !== undefined) {
    opcoes.headers = { 'Content-Type': 'application/json' };
    opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await fetch(caminho, opcoes);
  const tempos = resposta.headers.get('server-timing') || '';
  const numero = (re) => { const m = re.exec(tempos); return m ? parseFloat(m[1]) : null; };
  const tipo = resposta.headers.get('content-type') || '';
  return {
    ok: resposta.ok,
    status: resposta.status,
    dados: tipo.includes('json') ? await resposta.json() : await resposta.text(),
    consultas: Number(resposta.headers.get('x-consultas-sql')),
    banco: numero(/banco;dur=([\d.]+)/),
    total: numero(/total;dur=([\d.]+)/),
    cache: resposta.headers.get('x-cache'),
    invalidado: resposta.headers.get('x-cache-invalidado'),
  };
}

async function ocupado(botao, tarefa) {
  const botoes = document.querySelectorAll('button');
  botoes.forEach((b) => { b.disabled = true; });
  const texto = botao.textContent;
  botao.textContent = 'Aguarde…';
  try { await tarefa(); } catch (erro) { alert(`Erro: ${erro.message}`); } finally {
    botao.textContent = texto;
    botoes.forEach((b) => { b.disabled = false; });
  }
}

// ------------------------------------------------------------------ abas
document.querySelectorAll('.aba').forEach((aba) => aba.addEventListener('click', () => {
  document.querySelectorAll('.aba').forEach((a) => a.classList.toggle('ativa', a === aba));
  document.querySelectorAll('.painel').forEach((p) => p.classList.toggle('ativo', p.id === aba.dataset.aba));
}));

async function carregarEstado() {
  try {
    const { dados } = await chamar('GET', '/api/laboratorio/estado');
    $('estado').textContent = `API no ar · ${fmt(dados.tabelas.emprestimo)} empréstimos, ${fmt(dados.tabelas.livro)} livros, `
      + `${fmt(dados.tabelas.leitor)} leitores · PostgreSQL ${dados.banco.versao} no Supabase · cache Redis com TTL de `
      + `${dados.configuracao.cache_ttl_segundos} s`;
  } catch {
    $('estado').textContent = 'A API não respondeu. Rode "docker compose up -d" na pasta do projeto.';
  }
}

// ------------------------------------------------------------------ 1. cache
let contador = 0;
const livro = () => Number($('livro').value);

function guardarTituloOriginal(id, titulo) {
  const chave = `titulo-original-${id}`;
  try { if (!localStorage.getItem(chave)) localStorage.setItem(chave, titulo); } catch { /* sem armazenamento */ }
}

function tituloOriginal(id) {
  try { return localStorage.getItem(`titulo-original-${id}`); } catch { return null; }
}

async function atualizarTtl(id) {
  const { dados } = await chamar('GET', `/api/laboratorio/cache/livros/${id}`);
  $('m-ttl').textContent = dados.no_cache ? `${dados.ttl_restante_segundos} s` : 'fora do cache';
}

function registrar(operacao, r, etiqueta, classe) {
  const corpo = $('historico-cache');
  corpo.querySelector('.vazio')?.remove();
  contador += 1;
  const titulo = r.dados && r.dados.titulo ? r.dados.titulo : '—';
  corpo.insertAdjacentHTML('beforeend', `<tr><td>${contador}</td><td>${esc(operacao)}</td>`
    + `<td><span class="etiqueta ${classe}">${esc(etiqueta)}</span></td><td class="n">${r.consultas}</td>`
    + `<td class="n">${ms(r.banco)}</td><td class="n">${ms(r.total)}</td><td>${esc(titulo)}</td></tr>`);
}

function mostrarFicha(r, selo, classe, detalhe) {
  $('selo-cache').textContent = selo;
  $('selo-cache').className = `selo ${classe}`;
  $('m-consultas').textContent = r.consultas;
  $('m-banco').textContent = ms(r.banco);
  $('m-total').textContent = ms(r.total);
  $('detalhe-cache').innerHTML = detalhe;
}

async function lerFicha(comCache) {
  const id = livro();
  const r = await chamar('GET', `/api/livros/${id}/${comCache ? 'com-cache' : 'sem-cache'}`);
  if (!r.ok) throw new Error(r.dados.detail || `HTTP ${r.status}`);
  if (!tituloOriginal(id) || contador === 0) guardarTituloOriginal(id, r.dados.titulo);
  const hora = new Date(r.dados.gerada_em).toLocaleTimeString('pt-BR');
  const detalhe = `Livro ${id}: <strong>${esc(r.dados.titulo)}</strong> · ficha montada às ${hora}`
    + (r.cache === 'HIT' ? ' (a mesma hora de antes: veio do cache, sem tocar no banco)' : '');
  if (comCache) {
    mostrarFicha(r, r.cache, r.cache === 'HIT' ? 'hit' : 'miss', detalhe);
    registrar('GET ficha com cache', r, r.cache, r.cache === 'HIT' ? 'hit' : 'miss');
  } else {
    mostrarFicha(r, 'SEM CACHE', '', detalhe);
    registrar('GET ficha sem cache', r, 'banco', 'banco');
  }
  await atualizarTtl(id);
}

async function alterarTitulo(titulo, operacao) {
  const id = livro();
  const r = await chamar('PUT', `/api/livros/${id}`, { titulo });
  if (!r.ok) throw new Error(JSON.stringify(r.dados.detail || r.dados));
  mostrarFicha(r, 'PUT', 'put', `Título alterado para <strong>${esc(titulo)}</strong>. Cabeçalho X-Cache-Invalidado: `
    + `<strong>${esc(r.invalidado)}</strong> — a ficha foi apagada do cache depois do commit.`);
  registrar(operacao, r, `invalidou: ${r.invalidado}`, 'put');
  await atualizarTtl(id);
}

$('btn-sem-cache').addEventListener('click', (e) => ocupado(e.target, () => lerFicha(false)));
$('btn-com-cache').addEventListener('click', (e) => ocupado(e.target, () => lerFicha(true)));
$('btn-alterar').addEventListener('click', (e) => ocupado(e.target, async () => {
  const id = livro();
  if (!tituloOriginal(id)) {
    const r = await chamar('GET', `/api/livros/${id}/sem-cache`);
    guardarTituloOriginal(id, r.dados.titulo);
  }
  await alterarTitulo($('novo-titulo').value.trim() || 'Novo título', 'PUT alterar título');
}));
$('btn-restaurar').addEventListener('click', (e) => ocupado(e.target, async () => {
  const original = tituloOriginal(livro());
  if (!original) throw new Error('o título original deste livro ainda não foi lido nesta máquina');
  await alterarTitulo(original, 'PUT restaurar título');
}));
$('btn-esvaziar').addEventListener('click', (e) => ocupado(e.target, async () => {
  const { dados } = await chamar('DELETE', '/api/laboratorio/cache');
  $('selo-cache').textContent = 'VAZIO';
  $('selo-cache').className = 'selo';
  $('detalhe-cache').textContent = `Cache esvaziado (${dados.chaves_removidas} fichas removidas). A próxima leitura com cache será MISS.`;
  await atualizarTtl(livro());
}));

// ------------------------------------------------------------------ 2. LAZY x EAGER
const ESTRATEGIAS = [
  ['lazy', 'LAZY (lazy="select")'],
  ['eager', 'EAGER (lazy="joined")'],
  ['eager-selectin', 'EAGER com selectinload'],
  ['eager-immediate', 'EAGER com immediateload'],
  ['join-fetch', 'JOIN FETCH (joinedload)'],
  ['otimizada', 'Otimizada (projeção)'],
  ['nativa', 'SQL nativo'],
];

function desenharEstrategias() {
  $('tabela-estrategias').innerHTML = ESTRATEGIAS.map(([chave, nome]) => `<tr id="linha-${chave}"><td>${esc(nome)}</td>`
    + '<td class="n">—</td><td><div class="barra" style="width:0"></div></td><td class="n">—</td><td class="n">—</td>'
    + `<td><button data-sql="${chave}">Ver SQL</button></td></tr>`).join('');
  document.querySelectorAll('[data-sql]').forEach((b) => b.addEventListener('click', (e) => ocupado(e.target, () => verSql(b.dataset.sql))));
}

async function compararEstrategias() {
  const quantidade = $('quantidade').value;
  const resultados = {};
  for (const [chave] of ESTRATEGIAS) {
    const linha = $(`linha-${chave}`);
    linha.classList.add('rodando');
    const r = await chamar('GET', `/api/emprestimos/${chave}?desde_id=1000&quantidade=${quantidade}`);
    resultados[chave] = r;
    linha.classList.remove('rodando');
    const celulas = linha.querySelectorAll('td');
    celulas[1].textContent = r.consultas;
    celulas[3].textContent = ms(r.banco);
    celulas[4].textContent = ms(r.total);
    const maior = Math.max(...Object.values(resultados).map((x) => x.consultas));
    Object.entries(resultados).forEach(([c, x]) => {
      const barra = $(`linha-${c}`).querySelector('.barra');
      barra.style.width = `${Math.max(2, (x.consultas / Math.max(maior, 1)) * 100)}%`;
      barra.classList.toggle('uma', x.consultas === 1);
    });
  }
}

async function verSql(chave) {
  const { dados } = await chamar('GET', `/api/laboratorio/sql/emprestimos/${chave}?desde_id=150000&quantidade=3`);
  const nome = ESTRATEGIAS.find(([c]) => c === chave)[1];
  $('cartao-sql').hidden = false;
  $('titulo-sql').textContent = `SQL executado pela estratégia ${nome}, para uma página de 3 empréstimos`;
  const colunas = [...new Set(dados.comandos.map((c) => c.colunas))].join(', ');
  $('resumo-sql').innerHTML = `<strong>${dados.consultas} ${dados.consultas === 1 ? 'consulta' : 'consultas'}</strong> · `
    + `${fmt(dados.linhas_lidas_do_banco)} linhas e ${fmt(dados.bytes_lidos_do_banco)} bytes lidos do banco · `
    + `colunas por linha: <strong>${colunas}</strong> · resposta da API: ${fmt(dados.bytes_da_resposta)} bytes (igual em todas)`;
  $('lista-sql').innerHTML = dados.comandos.map((c) => {
    const sql = c.sql.replace(/\s+/g, ' ').trim();
    const curto = sql.length > 230 ? `${sql.slice(0, 230)} …` : sql;
    return `<li><code>${esc(curto)}</code><span class="info">${c.linhas} ${c.linhas === 1 ? 'linha' : 'linhas'}, `
      + `${c.colunas} colunas, ${fmt(c.bytes)} bytes, ${ms(c.duracao_ms)}</span></li>`;
  }).join('');
  $('cartao-sql').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('btn-comparar').addEventListener('click', (e) => ocupado(e.target, compararEstrategias));

// ------------------------------------------------------------------ 3. índices
const INDICE = 'idx_emprestimo_leitor_data';

async function listarIndices() {
  const { dados } = await chamar('GET', '/api/laboratorio/indices');
  $('lista-indices').innerHTML = dados.map((i) => `<span class="chip ${i.nome === INDICE ? 'novo' : ''}">${esc(i.nome)} `
    + `(${fmt(i.bytes / 1048576, 1)} MB)</span>`).join('');
}

function destacarPlano(linhas) {
  return linhas.map((l) => esc(l)
    .replace(/(Parallel Seq Scan|Seq Scan|Rows Removed by Filter: \d+|Sort Key: [^\n]+|Sort Method[^\n]*)/g, '<span class="ruim">$1</span>')
    .replace(new RegExp(`(Index Scan using ${INDICE}|Execution Time: [\\d.]+ ms)`, 'g'), '<span class="bom">$1</span>'))
    .join('\n');
}

async function explicar() {
  const r = await chamar('GET', `/api/laboratorio/explain/historico?leitor_id=${Number($('leitor').value)}`);
  const d = r.dados;
  const comIndice = d.indices_usados.includes(INDICE);
  const varredura = d.tabelas_lidas_por_inteiro.length ? `Seq Scan (lê a tabela ${d.tabelas_lidas_por_inteiro.join(', ')} inteira)` : `Index Scan em ${INDICE}`;
  $(comIndice ? 'plano-com' : 'plano-sem').innerHTML = `<h2>${comIndice ? 'Com o índice' : 'Sem o índice'}</h2>`
    + '<div class="metricas">'
    + `<div><span class="rotulo">Tempo de execução no banco</span><span class="valor">${ms(d.tempo_de_execucao_ms)}</span></div>`
    + `<div><span class="rotulo">Ordenação (Sort)</span><span class="valor">${d.tem_ordenacao ? 'sim' : 'não'}</span></div></div>`
    + `<p class="detalhe"><strong>${esc(varredura)}</strong> · índices usados: ${d.indices_usados.map(esc).join(', ') || 'nenhum'}</p>`
    + `<pre class="plano">${destacarPlano(d.plano)}</pre>`;
}

async function mudarIndice(metodo) {
  await chamar(metodo, '/api/laboratorio/indices/leitor-data');
  await listarIndices();
}

$('btn-explain').addEventListener('click', (e) => ocupado(e.target, explicar));
$('btn-criar-indice').addEventListener('click', (e) => ocupado(e.target, () => mudarIndice('PUT')));
$('btn-remover-indice').addEventListener('click', (e) => ocupado(e.target, () => mudarIndice('DELETE')));
$('btn-historico').addEventListener('click', (e) => ocupado(e.target, async () => {
  const id = Number($('leitor').value);
  const r = await chamar('GET', `/api/leitores/${id}/emprestimos`);
  $('resultado-historico').innerHTML = `Histórico do leitor ${id} pela API: <strong>${r.dados.quantidade} empréstimos</strong>, `
    + `${r.consultas} consulta, ${ms(r.banco)} no banco e ${ms(r.total)} no servidor. A maior parte é a viagem até o banco `
    + '(~150 ms); o ganho do índice aparece sob carga.';
}));

// ------------------------------------------------------------------ em volume (abas 1, 2 e 3)
// Muitas requisições seguidas, 6 ao mesmo tempo (como um navegador), para a diferença acumulada aparecer.
const seg = (n) => `${fmt(n / 1000, n < 10000 ? 2 : 1)} s`;
const progresso = (id, rotulo) => (feitos, n) => { $(id).textContent = `${rotulo}: ${feitos} de ${n}…`; };

async function emLote(n, simultaneas, tarefa, aviso) {
  const resultados = new Array(n);
  let proximo = 0;
  let feitos = 0;
  const inicio = performance.now();
  async function trabalhador() {
    while (proximo < n) {
      const i = proximo++;
      resultados[i] = await tarefa(i);
      feitos += 1;
      if (aviso) aviso(feitos, n);
    }
  }
  await Promise.all(Array.from({ length: Math.min(simultaneas, n) }, trabalhador));
  return { resultados, totalMs: performance.now() - inicio };
}

function resumoLote(nome, lote, extra = '') {
  const r = lote.resultados;
  return {
    nome,
    n: r.length,
    totalMs: lote.totalMs,
    mediaMs: r.reduce((s, x) => s + (x.total || 0), 0) / r.length,
    rps: r.length / (lote.totalMs / 1000),
    consultas: r.reduce((s, x) => s + (x.consultas || 0), 0),
    extra,
  };
}

function mostrarVolume(alvo, linhas, frase, rotulos = {}) {
  const t = { total: 'Tempo total', media: 'Média por requisição', ritmo: 'Requisições/s', consultas: 'Consultas SQL somadas', ...rotulos };
  const maior = Math.max(...linhas.map((l) => l.totalMs));
  const menor = Math.min(...linhas.map((l) => l.totalMs));
  $(alvo).innerHTML = `<div class="cartao"><p class="frase">${frase}</p><table><thead><tr><th>Versão</th>`
    + `<th class="n">Requisições</th><th class="n">${t.total}</th><th class="barra-col">${t.total}</th>`
    + `<th class="n">${t.media}</th><th class="n">${t.ritmo}</th><th class="n">${t.consultas}</th>`
    + `${t.extra ? `<th class="n">${t.extra}</th>` : ''}<th class="n">Comparado ao mais lento</th></tr></thead><tbody>`
    + linhas.map((l) => `<tr><td>${esc(l.nome)}</td><td class="n">${l.n}</td><td class="n">${seg(l.totalMs)}</td>`
      + `<td><div class="barra-tempo ${l.totalMs === menor ? 'melhor' : ''}" style="width:${Math.max(1, (l.totalMs / maior) * 100)}%"></div></td>`
      + `<td class="n">${ms(l.mediaMs)}</td><td class="n">${fmt(l.rps, 1)}</td><td class="n">${fmt(l.consultas)}</td>`
      + `${t.extra ? `<td class="n">${l.extra}</td>` : ''}`
      + `<td class="n ganho">${l.totalMs === maior ? '—' : `${fmt(maior / l.totalMs, 1)}× mais rápido`}</td></tr>`).join('')
    + '</tbody></table></div>';
}

$('btn-vol-cache').addEventListener('click', (e) => ocupado(e.target, async () => {
  const n = Number($('vol-cache-n').value);
  const livros = Number($('vol-cache-livros').value);
  const id = (i) => 1000 + (i % livros) * 37; // livros fora da demonstração: o 42 não é tocado
  await chamar('DELETE', '/api/laboratorio/cache');
  const sem = await emLote(n, 6, (i) => chamar('GET', `/api/livros/${id(i)}/sem-cache?r=${i}`), progresso('prog-cache', 'Sem cache'));
  const com = await emLote(n, 6, (i) => chamar('GET', `/api/livros/${id(i)}/com-cache?r=${i}`), progresso('prog-cache', 'Com cache'));
  await chamar('DELETE', '/api/laboratorio/cache');
  const acertos = com.resultados.filter((r) => r.cache === 'HIT').length;
  const a = resumoLote('Sem cache', sem, '—');
  const b = resumoLote('Com cache (começa vazio)', com, `${acertos} de ${n}`);
  $('prog-cache').textContent = 'Concluído. O cache foi esvaziado no fim, para não atrapalhar a demonstração.';
  mostrarVolume('vol-cache', [a, b], `${n} leituras de ${livros} ${livros === 1 ? 'livro' : 'livros'}: `
    + `<strong>${seg(b.totalMs)}</strong> com cache contra ${seg(a.totalMs)} sem cache — <strong>${fmt(a.totalMs / b.totalMs, 1)}× `
    + `mais rápido</strong>, ${fmt(a.consultas - b.consultas)} consultas a menos ao banco e ${seg(a.totalMs - b.totalMs)} economizados.`,
  { extra: 'Acertos no cache' });
}));

$('btn-vol-emp').addEventListener('click', (e) => ocupado(e.target, async () => {
  const n = Number($('vol-emp-n').value);
  const q = Number($('vol-emp-q').value);
  const escolhidas = q <= 20 ? ['lazy', 'eager', 'otimizada'] : ['eager', 'join-fetch', 'otimizada', 'nativa'];
  const linhas = [];
  for (const chave of escolhidas) {
    const nome = ESTRATEGIAS.find(([c]) => c === chave)[1];
    const lote = await emLote(n, 6, (i) => chamar('GET', `/api/emprestimos/${chave}?desde_id=${1000 + i * q}&quantidade=${q}`),
      progresso('prog-emp', nome));
    let lido = '—';
    if (chave !== 'lazy') {
      const { dados } = await chamar('GET', `/api/laboratorio/sql/emprestimos/${chave}?desde_id=1000&quantidade=${q}`);
      lido = `${fmt(dados.bytes_lidos_do_banco / 1024, 1)} KB`;
    }
    linhas.push(resumoLote(nome, lote, lido));
  }
  $('prog-emp').textContent = 'Concluído.';
  const pior = linhas.reduce((x, y) => (x.totalMs > y.totalMs ? x : y));
  const melhor = linhas.reduce((x, y) => (x.totalMs < y.totalMs ? x : y));
  mostrarVolume('vol-emp', linhas, `${n} páginas de ${q} empréstimos: <strong>${esc(melhor.nome)}</strong> em `
    + `<strong>${seg(melhor.totalMs)}</strong> contra ${seg(pior.totalMs)} do ${esc(pior.nome)} — `
    + `<strong>${fmt(pior.totalMs / melhor.totalMs, 1)}× mais rápido</strong>.`, { extra: 'Lido do banco por página' });
}));

$('btn-vol-idx').addEventListener('click', (e) => ocupado(e.target, async () => {
  const n = Number($('vol-idx-n').value);
  const leitor = (i) => 1 + ((i * 197) % 10000);
  const antes = (await chamar('GET', '/api/laboratorio/indices')).dados.some((i) => i.nome === INDICE);
  const rodada = async (nome) => {
    const lote = await emLote(n, 6, (i) => chamar('GET', `/api/laboratorio/explain/historico?leitor_id=${leitor(i)}`),
      progresso('prog-idx', nome));
    const banco = lote.resultados.reduce((s, r) => s + r.dados.tempo_de_execucao_ms, 0);
    const varreduras = lote.resultados.filter((r) => r.dados.tabelas_lidas_por_inteiro.length).length;
    return { nome, n, totalMs: banco, mediaMs: banco / n, rps: n / (lote.totalMs / 1000), consultas: n, extra: `${varreduras} de ${n}` };
  };
  await chamar('DELETE', '/api/laboratorio/indices/leitor-data');
  const sem = await rodada('Sem índice');
  await chamar('PUT', '/api/laboratorio/indices/leitor-data');
  const com = await rodada('Com o índice (leitor_id, data_emprestimo DESC)');
  if (!antes) await chamar('DELETE', '/api/laboratorio/indices/leitor-data');
  await listarIndices();
  $('prog-idx').textContent = antes ? 'Concluído.' : 'Concluído. O índice foi removido no fim, como estava antes.';
  mostrarVolume('vol-idx', [sem, com], `${n} leitores: o banco trabalhou <strong>${ms(com.totalMs)}</strong> com o índice `
    + `contra ${ms(sem.totalMs)} sem ele — <strong>${fmt(sem.totalMs / com.totalMs, 0)}× menos trabalho</strong>. Sem o índice, `
    + `${sem.extra} consultas leram a tabela inteira (Seq Scan).`,
  { total: 'Tempo de execução somado no banco', media: 'Média por consulta no banco', ritmo: 'EXPLAIN/s', consultas: 'Consultas', extra: 'Leram a tabela inteira' });
}));

// ------------------------------------------------------------------ 4. carga
$('btn-copiar').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('comando-k6').textContent);
    $('copiado').textContent = 'Copiado. Cole no terminal aberto na pasta do projeto.';
  } catch {
    $('copiado').textContent = 'Selecione o comando e copie com Ctrl+C.';
  }
});

desenharEstrategias();
carregarEstado();
listarIndices();

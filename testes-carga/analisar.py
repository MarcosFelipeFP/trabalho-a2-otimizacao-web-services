"""Tabelas e gráficos dos testes de desempenho, a partir de uma pasta de resultados.

    python testes-carga/analisar.py testes-carga/resultados/<data e hora>

Lê execucoes.csv (uma linha por nível de carga de cada execução do k6), ambiente.json, k6/,
banco/ e cache/, e grava resumo.md e graficos/*.svg na mesma pasta. Cada número das tabelas é a
média das repetições; a coluna "variação" mostra a maior distância entre uma repetição e a
média da vazão, em %. Só usa a biblioteca padrão.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from graficos import br, figura

NOMES = {
    'sem-cache': 'sem cache', 'com-cache-frio': 'cache frio', 'com-cache-quente': 'cache quente',
    'lazy': 'LAZY', 'eager': 'EAGER', 'otimizada': 'otimizada', 'nativa': 'SQL nativo',
    'sem-indice': 'sem índice', 'com-indice': 'com índice',
}
TITULOS = {
    'cache': 'Cenário 1: ficha do livro sem e com cache',
    'persistencia': 'Cenário 2: página de 20 empréstimos com livro e leitor',
    'indice': 'Cenário 3: histórico de empréstimos de um leitor, sem e com índice',
}
ORDEM = {
    'cache': ['sem-cache', 'com-cache-frio', 'com-cache-quente'],
    'persistencia': ['lazy', 'eager', 'otimizada', 'nativa'],
    'indice': ['sem-indice', 'com-indice'],
}
METRICAS = [
    'vazao_rps', 'latencia_media_ms', 'latencia_mediana_ms', 'latencia_p90_ms', 'latencia_p95_ms',
    'latencia_p99_ms', 'latencia_max_ms', 'taxa_de_erros', 'consultas_sql_por_req', 'tempo_no_banco_ms',
    'tempo_no_servidor_ms', 'taxa_de_acerto_cache', 'kb_por_req', 'cpu_api_pct', 'cpu_banco_pct',
    'cpu_cache_pct', 'cpu_k6_pct', 'cpu_outros_pct', 'mem_api_mb', 'mem_banco_mb', 'mem_cache_mb',
]


def numero(texto):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def media(valores):
    valores = [v for v in valores if v is not None]
    return mean(valores) if valores else None


def ler_execucoes(pasta):
    with open(pasta / 'execucoes.csv', encoding='utf-8') as arquivo:
        return list(csv.DictReader(arquivo))


def agrupar(linhas):
    """(cenário, versão, ttl, vus) -> médias das repetições, mais a variação da vazão."""
    grupos = defaultdict(list)
    for linha in linhas:
        grupos[(linha['cenario'], linha['versao'], linha['ttl_s'], int(linha['vus']))].append(linha)
    resultado = {}
    for chave, repeticoes in grupos.items():
        valores = {m: media([numero(r[m]) for r in repeticoes]) for m in METRICAS}
        vazoes = [numero(r['vazao_rps']) for r in repeticoes if numero(r['vazao_rps'])]
        valores['variacao_pct'] = (max(abs(v - valores['vazao_rps']) for v in vazoes) / valores['vazao_rps'] * 100
                                   if len(vazoes) > 1 and valores['vazao_rps'] else None)
        valores['repeticoes'] = len(repeticoes)
        valores['limites_ok'] = all(r['limites_ok'] == 'True' for r in repeticoes)
        resultado[chave] = valores
    return resultado


def f(valor, casas=1, sufixo=''):
    return '–' if valor is None else br(valor, casas) + sufixo


def ms(valor):
    if valor is None:
        return '–'
    return br(valor, 2 if valor < 10 else 1 if valor < 100 else 0)


def pct(valor, casas=0):
    return '–' if valor is None else br(valor * 100, casas) + '%'


# --------------------------------------------------------------------------- dados do banco

def resumo_do_banco(pasta, nome_do_arquivo):
    """Comando SQL principal da execução e contadores do PostgreSQL por requisição."""
    base = nome_do_arquivo.removesuffix('.json')
    caminho_banco, caminho_k6 = pasta / 'banco' / f'{base}.json', pasta / 'k6' / f'{base}.json'
    if not caminho_banco.exists() or not caminho_k6.exists():
        return None
    banco = json.loads(caminho_banco.read_text(encoding='utf-8'))
    requisicoes = json.loads(caminho_k6.read_text(encoding='utf-8')).get('requisicoes_ao_endpoint') or 0
    if not requisicoes:
        return None
    comandos = [c for c in banco['comandos'] if 'pg_stat' not in c['comando'] and 'pg_database' not in c['comando']]
    consultas = [c for c in comandos if c['comando'].split()[0].upper() not in ('BEGIN', 'COMMIT', 'ROLLBACK')]
    principal = max(consultas, key=lambda c: c['tempo_total_ms'], default=None)
    return {
        'linhas_percorridas_por_req': banco['banco']['linhas_percorridas'] / requisicoes,
        'blocos_por_req': banco['banco']['blocos_em_memoria'] / requisicoes,
        'tempo_de_banco_por_req_ms': sum(c['tempo_total_ms'] for c in comandos) / requisicoes,
        'principal': principal,
    }


# --------------------------------------------------------------------------- seções do resumo

def secao_ambiente(ambiente):
    api = ambiente['api']
    maquina = ambiente['maquina']
    parametros = ambiente['parametros']
    tabelas = ', '.join(f'{nome} {br(qtd)}' for nome, qtd in api['tabelas'].items())
    versoes = api['versoes']
    bibliotecas = ', '.join(f'{nome} {versao}' for nome, versao in versoes['bibliotecas_python'].items())
    outros = [c for c in ambiente.get('conteineres_em_execucao', []) if not c.startswith('biblioteca-')]
    linhas = [
        '## Ambiente',
        '',
        f'- Data: {ambiente["data"].replace("T", " ")}',
        f'- Máquina: {maquina["processador"]}, {maquina["nucleos_logicos"]} núcleos lógicos, '
        f'{br(maquina["memoria_gb"], 1)} GB; {maquina["sistema"]}',
        f'- Docker: {ambiente["docker"]}',
        f'- k6: {" ".join(ambiente["k6"] or ["?"])} ({"contêiner na rede da API" if parametros["k6"] == "docker" else "instalado na máquina"})',
        f'- API: Python {versoes["python"]}, {api["configuracao"]["workers"]} processos, '
        f'{api["configuracao"]["conexoes_por_worker"]} conexões por processo; {bibliotecas}',
        f'- Banco: PostgreSQL {versoes["postgresql"].split()[0]} ({api["tamanho_do_banco"]}); cache: Redis {versoes["redis"]}',
        f'- Dados: {tabelas}',
        f'- Cargas: {parametros["cargas"]} VUs; {parametros["aquecimento"]} s de aquecimento e '
        f'{parametros["duracao"]} s de medição por nível; {parametros["repeticoes"]} repetições',
        f'- Outros contêineres em execução: {", ".join(outros) if outros else "nenhum"}',
        '',
    ]
    return linhas


def secao_cenario(cenario, grupos, linhas_csv, pasta):
    chaves = sorted({k[3] for k in grupos if k[0] == cenario})
    versoes = [v for v in ORDEM[cenario] if any(k[0] == cenario and k[1] == v for k in grupos)]
    if not versoes:
        return []
    cache = cenario == 'cache'
    saida = [f'## {TITULOS[cenario]}', '']
    cabecalho = ['VUs', 'versão', 'req/s', 'média (ms)', 'p95 (ms)', 'p99 (ms)', 'erros']
    cabecalho += ['acertos no cache'] if cache else []
    cabecalho += ['SQL por req.', 'CPU API', 'CPU banco', 'variação']
    alinhamento = ['---:', '---'] + ['---:'] * (len(cabecalho) - 2)  # VUs, versão, números
    saida += ['| ' + ' | '.join(cabecalho) + ' |', '|' + '|'.join(alinhamento) + '|']
    for vus in chaves:
        for versao in versoes:
            g = grupos.get((cenario, versao, '', vus))
            if not g:
                continue
            celulas = [str(vus), NOMES[versao], f(g['vazao_rps'], 0), ms(g['latencia_media_ms']),
                       ms(g['latencia_p95_ms']), ms(g['latencia_p99_ms']), pct(g['taxa_de_erros'], 2)]
            celulas += [pct(g['taxa_de_acerto_cache'])] if cache else []
            celulas += [f(g['consultas_sql_por_req'], 1), f(g['cpu_api_pct'], 0, '%'), f(g['cpu_banco_pct'], 0, '%'),
                        '–' if g['variacao_pct'] is None else '±' + br(g['variacao_pct'], 1) + '%']
            saida.append('| ' + ' | '.join(celulas) + ' |')
    saida.append('')
    saida.append('CPU em % de um núcleo (400% = quatro núcleos ocupados). Variação: maior distância entre '
                 'a vazão de uma repetição e a média.')
    saida.append('')

    # comportamento do banco, pela média das execuções de cada versão
    blocos = []
    for versao in versoes:
        arquivos = sorted({l['arquivo'] for l in linhas_csv if l['cenario'] == cenario and l['versao'] == versao})
        dados = [d for d in (resumo_do_banco(pasta, a) for a in arquivos) if d]
        if not dados:
            continue
        principal = dados[0]['principal']
        blocos.append((versao, media([d['linhas_percorridas_por_req'] for d in dados]),
                       media([d['blocos_por_req'] for d in dados]),
                       media([d['tempo_de_banco_por_req_ms'] for d in dados]),
                       principal))
    if blocos:
        saida += ['Comportamento do banco (PostgreSQL), por requisição, em todas as execuções da versão:', '',
                  '| versão | linhas percorridas | blocos lidos (memória) | tempo de execução no banco (ms) | comando mais custoso |',
                  '|---|---:|---:|---:|---|']
        for versao, linhas_lidas, blocos_lidos, tempo, principal in blocos:
            comando = (principal or {}).get('comando', '')
            comando = (comando[:90] + '…') if len(comando) > 90 else comando
            saida.append(f'| {NOMES[versao]} | {br(linhas_lidas, 0)} | {br(blocos_lidos, 0)} | '
                         f'{br(tempo, 3)} | ' + (f'`{comando}`' if comando else 'nenhum: o banco não foi consultado')
                         + ' |')
        saida.append('')

    falhas = [(versao, vus) for (c, versao, _, vus), g in grupos.items() if c == cenario and not g['limites_ok']]
    if falhas:
        lista = ', '.join(f'{NOMES[v]} com {vus} VUs' for v, vus in sorted(falhas, key=lambda x: (x[1], x[0])))
        saida += [f'Limites do k6 (p95 < 500 ms, p99 < 1 s, erros < 1%) estourados em: {lista}.', '']
    else:
        saida += ['Todos os níveis respeitaram os limites do k6 (p95 < 500 ms, p99 < 1 s, erros < 1%).', '']

    saida.append(f'![{TITULOS[cenario]}](graficos/{cenario}.svg)')
    saida.append('')
    return saida


def grafico_cenario(cenario, grupos, pasta):
    chaves = sorted({k[3] for k in grupos if k[0] == cenario})
    versoes = [v for v in ORDEM[cenario] if any(k[0] == cenario and k[1] == v for k in grupos)]
    if not versoes:
        return

    def serie(metrica):
        return {NOMES[v]: [(grupos.get((cenario, v, '', vus)) or {}).get(metrica) for vus in chaves]
                for v in versoes}

    paineis = [
        {'titulo': 'Vazão', 'unidade': 'req/s', 'valores': serie('vazao_rps')},
        {'titulo': 'Latência média', 'unidade': 'ms', 'valores': serie('latencia_media_ms')},
        {'titulo': 'Latência p95', 'unidade': 'ms', 'valores': serie('latencia_p95_ms')},
        {'titulo': 'Latência p99', 'unidade': 'ms', 'valores': serie('latencia_p99_ms')},
        {'titulo': 'CPU da API (% de um núcleo)', 'unidade': '%', 'valores': serie('cpu_api_pct')},
        {'titulo': 'CPU do banco (% de um núcleo)', 'unidade': '%', 'valores': serie('cpu_banco_pct')},
    ]
    figura(pasta / 'graficos' / f'{cenario}.svg', TITULOS[cenario],
           'Média das repetições em cada nível de carga', chaves, 'usuários virtuais (VUs)',
           [NOMES[v] for v in versoes], paineis)


# --------------------------------------------------------------------------- experimento do TTL

def taxa_ao_longo_do_tempo(arquivo, janela=5):
    """Taxa de acerto a cada `janela` segundos, contada a partir do último esvaziamento do cache."""
    with open(arquivo, encoding='utf-8') as entrada:
        leituras = [(float(l['t']), int(l['acertos']), int(l['falhas'])) for l in csv.DictReader(entrada)]
    inicio = 0
    for i in range(1, len(leituras)):  # o contador volta a zero quando o cache é esvaziado
        if leituras[i][1] + leituras[i][2] < leituras[i - 1][1] + leituras[i - 1][2]:
            inicio = i
    leituras = leituras[inicio:]
    if len(leituras) < 2:
        return []
    t0 = leituras[0][0]
    taxas, limite, anterior = [], t0 + janela, leituras[0]
    for leitura in leituras[1:]:
        if leitura[0] >= limite:
            acertos, falhas = leitura[1] - anterior[1], leitura[2] - anterior[2]
            taxas.append(acertos / (acertos + falhas) if acertos + falhas else None)
            anterior, limite = leitura, limite + janela
    return taxas


def secao_ttl(grupos, linhas_csv, pasta):
    ttls = sorted({int(k[2]) for k in grupos if k[0] == 'ttl'})
    if not ttls:
        return []
    saida = ['## Efeito do TTL (cache começando vazio)', '',
             '| TTL | req/s | média (ms) | p95 (ms) | acertos no cache | acertos nos últimos 20 s | variação |',
             '|---:|---:|---:|---:|---:|---:|---:|']
    series = {}
    for ttl in ttls:
        chave = next(k for k in grupos if k[0] == 'ttl' and int(k[2]) == ttl)
        g = grupos[chave]
        arquivos = sorted({l['arquivo'] for l in linhas_csv if l['cenario'] == 'ttl' and l['ttl_s'] == str(ttl)})
        curvas = [taxa_ao_longo_do_tempo(pasta / 'cache' / a.replace('.json', '.csv'))
                  for a in arquivos if (pasta / 'cache' / a.replace('.json', '.csv')).exists()]
        curvas = [c for c in curvas if c]
        if curvas:
            tamanho = min(len(c) for c in curvas)
            series[f'TTL {ttl} s'] = [media([c[i] for c in curvas]) for i in range(tamanho)]
        finais = media([media(c[-4:]) for c in curvas]) if curvas else None
        saida.append(f'| {br(ttl)} s | {f(g["vazao_rps"], 0)} | {ms(g["latencia_media_ms"])} | '
                     f'{ms(g["latencia_p95_ms"])} | {pct(g["taxa_de_acerto_cache"])} | {pct(finais)} | '
                     + ('–' if g['variacao_pct'] is None else '±' + br(g['variacao_pct'], 1) + '%') + ' |')
    saida.append('')
    if series:
        pontos = min(len(v) for v in series.values())
        rotulos = [str(5 * (i + 1)) for i in range(pontos)]
        valores = {nome: [None if v is None else v * 100 for v in serie[:pontos]] for nome, serie in series.items()}
        figura(pasta / 'graficos' / 'ttl.svg', 'Taxa de acerto do cache ao longo do tempo, por TTL',
               'Cache esvaziado no instante 0; média das repetições, em janelas de 5 s',
               rotulos, 'segundos desde o esvaziamento', list(valores),
               [{'titulo': 'Acertos no cache', 'unidade': '%', 'valores': valores}])
        saida += ['![Taxa de acerto ao longo do tempo](graficos/ttl.svg)', '']
    return saida


# --------------------------------------------------------------------------- principal

def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    pasta = Path(sys.argv[1]).resolve()
    (pasta / 'graficos').mkdir(exist_ok=True)
    linhas = ler_execucoes(pasta)
    if not linhas:
        raise SystemExit('execucoes.csv está vazio.')
    grupos = agrupar(linhas)
    ambiente = json.loads((pasta / 'ambiente.json').read_text(encoding='utf-8'))

    resumo = ['# Resultados dos testes de desempenho', '',
              'Gerado por `testes-carga/analisar.py` a partir das execuções do k6 desta pasta.', '']
    resumo += secao_ambiente(ambiente)
    for cenario in ('cache', 'persistencia', 'indice'):
        resumo += secao_cenario(cenario, grupos, linhas, pasta)
        grafico_cenario(cenario, grupos, pasta)
    resumo += secao_ttl(grupos, linhas, pasta)
    (pasta / 'resumo.md').write_text('\n'.join(resumo), encoding='utf-8')
    print(f'Gravados {pasta / "resumo.md"} e os gráficos em {pasta / "graficos"}')


if __name__ == '__main__':
    main()

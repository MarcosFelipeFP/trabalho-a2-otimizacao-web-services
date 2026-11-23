"""Roteiro dos testes de desempenho (item 3 do trabalho).

Quem gera a carga e mede é o Grafana k6 (scripts em testes-carga/k6/). Cada script percorre os
níveis de carga, com aquecimento e medição em cada um, e confere os limites (thresholds). Este
roteiro só organiza a matriz de execuções:

  1. confere se a API está no ar, carrega o banco na memória, mede a ida e volta até o banco e
     registra o ambiente;
  2. aquece todos os endpoints uma vez;
  3. roda cada versão de cada cenário, com repetições e a ordem das versões alternada; antes de
     cada execução a API é recriada, para nenhuma começar com a fila de requisições deixada pela
     anterior (o LAZY sob carga alta deixa requisições na fila depois que o k6 desiste delas);
  4. durante as medições, lê a CPU e a memória dos contêineres locais (contadores do cgroup) e,
     a cada segundo, o tempo de execução acumulado no banco (pg_stat_statements, por um psql);
  5. guarda os comandos SQL de cada execução (diferença do pg_stat_statements entre o antes e o
     depois) e, nos cenários de cache, a taxa de acerto segundo a segundo;
  6. guarda o relatório HTML do painel web do k6 da primeira repetição de cada versão;
  7. no fim, chama o analisar.py, que monta as tabelas e os gráficos.

Uso, na pasta do projeto, com a API no ar (docker compose up -d):

    python testes-carga/executar.py                  matriz completa (cerca de 2 horas)
    python testes-carga/executar.py --rapido         conferência do roteiro (uns 15 minutos)
    python testes-carga/executar.py --cenarios indice --cargas 50 --repeticoes 1

Os resultados ficam em testes-carga/resultados/<data e hora>/. Só usa a biblioteca padrão.

A matriz pode ser rodada em partes: --minutos faz o roteiro parar antes de começar uma execução
que passaria do tempo dado, e --continuar retoma uma matriz parada (ou interrompida), pulando as
execuções que já estão em execucoes.csv e usando os mesmos parâmetros da primeira parte:

    python testes-carga/executar.py --minutos 9
    python testes-carga/executar.py --continuar testes-carga/resultados/<data e hora> --minutos 9
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent

VERSOES = {
    'cache': ['sem-cache', 'com-cache-frio', 'com-cache-quente'],
    'persistencia': ['lazy', 'eager', 'otimizada', 'nativa'],
    'indice': ['sem-indice', 'com-indice'],
}
SCRIPTS = {'cache': 'cache.js', 'persistencia': 'persistencia.js', 'indice': 'indice.js', 'ttl': 'cache.js'}
CONTEINERES = {
    'api': 'biblioteca-api', 'banco': 'biblioteca-banco', 'cache': 'biblioteca-cache', 'k6': 'biblioteca-k6',
}
AMOSTRADOR = 'biblioteca-amostrador'
AMOSTRADOR_DO_BANCO = 'biblioteca-amostrador-banco'
TTL_PADRAO = 600

COLUNAS = [
    'cenario', 'versao', 'ttl_s', 'repeticao', 'vus', 'requisicoes', 'vazao_rps',
    'latencia_media_ms', 'latencia_mediana_ms', 'latencia_p90_ms', 'latencia_p95_ms', 'latencia_p99_ms',
    'latencia_max_ms', 'taxa_de_erros', 'consultas_sql_por_req', 'tempo_no_banco_ms', 'tempo_no_servidor_ms',
    'taxa_de_acerto_cache', 'kb_por_req', 'banco_execucao_pct', 'banco_linhas_por_req',
    'banco_blocos_por_req', 'cpu_api_pct', 'cpu_banco_pct', 'cpu_cache_pct', 'cpu_k6_pct',
    'cpu_outros_pct', 'mem_api_mb', 'mem_banco_mb', 'mem_cache_mb', 'limites_ok', 'arquivo',
]


# --------------------------------------------------------------------------- API e Docker

class Api:
    def __init__(self, base):
        self.base = base.rstrip('/')

    def chamar(self, metodo, caminho, timeout=120):
        requisicao = urllib.request.Request(self.base + caminho, method=metodo)
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = resposta.read()
        return json.loads(corpo) if corpo else None

    def no_ar(self):
        try:
            return self.chamar('GET', '/api/saude', timeout=3).get('status') == 'ok'
        except OSError:
            return False

    def esperar(self, limite=120):
        fim = time.time() + limite
        while time.time() < fim:
            if self.no_ar():
                return
            time.sleep(1)
        raise SystemExit(f'A API não respondeu em {self.base} depois de {limite} s.')


def saida_de(comando, cwd=None):
    try:
        return subprocess.run(comando, capture_output=True, text=True, timeout=120, cwd=cwd).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def ids_dos_conteineres():
    """Nome -> os 12 primeiros caracteres do id, como aparecem no cgroup."""
    saida = saida_de(['docker', 'ps', '-a', '--no-trunc', '--format', '{{.ID}} {{.Names}}']) or ''
    ids = {}
    for linha in saida.splitlines():
        if ' ' in linha:
            identificador, nome = linha.split(' ', 1)
            ids[nome.strip()] = identificador[:12]
    return ids


def reiniciar_api(api, ttl):
    """Recria o contêiner da API (processos novos, sem fila e sem conexões abertas), com o TTL de
    cache pedido (variável CACHE_TTL_SEGUNDOS)."""
    ambiente = {**os.environ, 'CACHE_TTL_SEGUNDOS': str(ttl)}
    for tentativa in range(1, 4):
        r = subprocess.run(['docker', 'compose', 'up', '-d', '--force-recreate', '--no-deps', 'api'], cwd=RAIZ,
                           env=ambiente, capture_output=True, encoding='utf-8', errors='replace')
        if r.returncode == 0:
            break
        # o Docker Desktop às vezes falha ao recriar o contêiner, de forma passageira (aconteceu uma vez
        # na matriz com o banco local): espera e tenta de novo antes de desistir da matriz
        print(f'  a API não foi recriada (tentativa {tentativa} de 3): {r.stderr.strip()[-300:]}', flush=True)
        time.sleep(15)
    else:
        raise SystemExit('Não foi possível recriar o contêiner da API; retome com --continuar.')
    time.sleep(2)
    api.esperar()
    if api.chamar('GET', '/api/laboratorio/estado')['configuracao']['cache_ttl_segundos'] != ttl:
        raise SystemExit(f'A API não subiu com TTL de {ttl} s.')


# --------------------------------------------------------------------------- medição de recursos

class Amostrador:
    """A cada segundo, lê a CPU acumulada e a memória de todos os contêineres (cgroup v2 do Docker).

    Roda num contêiner à parte que enxerga /sys/fs/cgroup da máquina virtual do Docker. O relógio
    dele é o mesmo do contêiner do k6, então as janelas de medição do k6 se alinham às amostras.
    """

    CODIGO = '\n'.join([
        'import json, os, time',
        'raiz = "/cg/docker"',
        'while True:',
        '    agora = time.time()',
        '    leituras = {}',
        '    for nome in os.listdir(raiz):',
        '        if len(nome) != 64:',
        '            continue',
        '        try:',
        '            with open(f"{raiz}/{nome}/cpu.stat") as f:',
        '                usec = int(f.readline().split()[1])',
        '            with open(f"{raiz}/{nome}/memory.current") as f:',
        '                memoria = int(f.read())',
        '        except (OSError, ValueError, IndexError):',
        '            continue',
        '        leituras[nome[:12]] = [usec, memoria]',
        '    print(json.dumps({"t": agora, "c": leituras}), flush=True)',
        '    time.sleep(max(0.0, 1.0 - (time.time() - agora)))',
    ])

    def __init__(self):
        self.amostras = []
        self.trava = threading.Lock()
        self.processo = None

    def iniciar(self):
        subprocess.run(['docker', 'rm', '-f', AMOSTRADOR], capture_output=True)
        self.processo = subprocess.Popen(
            ['docker', 'run', '--rm', '--name', AMOSTRADOR, '-v', '/sys/fs/cgroup:/cg:ro',
             'python:3.14-slim', 'python', '-u', '-c', self.CODIGO],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._ler, daemon=True).start()
        fim = time.time() + 90
        while time.time() < fim and len(self.amostras) < 2:
            time.sleep(0.5)
        if len(self.amostras) < 2:
            print('  aviso: o amostrador de CPU e memória não respondeu; esses dados ficarão vazios.')

    def _ler(self):
        for linha in self.processo.stdout:
            try:
                dado = json.loads(linha)
            except ValueError:
                continue
            with self.trava:
                self.amostras.append((dado['t'], dado['c']))

    def parar(self):
        subprocess.run(['docker', 'rm', '-f', AMOSTRADOR], capture_output=True)

    def na_janela(self, inicio, fim):
        with self.trava:
            return [a for a in self.amostras if inicio <= a[0] <= fim]


def recursos(amostras, ids):
    """CPU média (% de um núcleo) e memória máxima (MB) de cada contêiner nas amostras."""
    if len(amostras) < 2:
        return {}
    (t0, inicio), (t1, fim) = amostras[0], amostras[-1]
    duracao = t1 - t0
    resultado, conhecidos = {}, {ids.get(AMOSTRADOR)}
    for chave, nome in CONTEINERES.items():
        identificador = ids.get(nome)
        if not identificador or identificador not in inicio or identificador not in fim:
            continue
        conhecidos.add(identificador)
        resultado[f'cpu_{chave}_pct'] = (fim[identificador][0] - inicio[identificador][0]) / (duracao * 1e4)
        if chave != 'k6':
            memorias = [c[identificador][1] for _, c in amostras if identificador in c]
            resultado[f'mem_{chave}_mb'] = max(memorias) / 2 ** 20
    outros = [i for i in fim if i in inicio and i not in conhecidos]
    resultado['cpu_outros_pct'] = sum(fim[i][0] - inicio[i][0] for i in outros) / (duracao * 1e4)
    return resultado


class AmostradorDoBanco:
    """A cada segundo, lê do banco o tempo de execução acumulado dos comandos da API
    (pg_stat_statements), por um psql que fica conectado (serviço psql do Docker Compose).

    A diferença entre duas leituras, dividida pelo intervalo, é a fração do tempo em que o banco
    esteve executando consultas da API: 100% equivale a um núcleo ocupado o tempo todo. Com os
    dados em memória, esse tempo é quase todo CPU. É a medida do comportamento do banco possível
    no Supabase, onde a CPU do servidor não é acessível ao usuário do banco."""

    CONSULTA = r"""SELECT coalesce(sum(calls), 0)::bigint, coalesce(sum(total_exec_time), 0)::float8,
       coalesce(sum(rows), 0)::bigint, coalesce(sum(shared_blks_hit), 0)::bigint,
       coalesce(sum(shared_blks_read), 0)::bigint
FROM pg_stat_statements
WHERE userid = (SELECT oid FROM pg_roles WHERE rolname = current_user)
  AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND query ~* '^\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\M'
  AND query ~* '\m(emprestimo|livro|leitor|autor|categoria)\M'
  AND query !~* 'pg_stat_statements|pg_prewarm|pg_class|pg_index|pg_roles'"""

    def __init__(self):
        self.amostras = []
        self.trava = threading.Lock()
        self.processo = None

    def iniciar(self):
        subprocess.run(['docker', 'rm', '-f', AMOSTRADOR_DO_BANCO], capture_output=True)
        # a consulta vai pela entrada padrão: o \watch repete o que está no buffer, e o -c não
        # deixa misturar SQL e comandos do psql
        self.processo = subprocess.Popen(
            ['docker', 'compose', 'run', '--rm', '-T', '--name', AMOSTRADOR_DO_BANCO, 'psql',
             '-At', '-F', '|'],
            cwd=RAIZ, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.processo.stdin.write(self.CONSULTA + '\n\\watch 1\n')
        self.processo.stdin.close()
        threading.Thread(target=self._ler, daemon=True).start()
        fim = time.time() + 60
        while time.time() < fim and len(self.amostras) < 2:
            time.sleep(0.5)
        if len(self.amostras) < 2:
            print('  aviso: o amostrador do banco não respondeu; o tempo de execução no banco ficará vazio.')

    def _ler(self):
        for linha in self.processo.stdout:
            partes = linha.strip().split('|')
            if len(partes) != 5:
                continue
            try:
                valores = [float(parte) for parte in partes]
            except ValueError:
                continue
            with self.trava:
                self.amostras.append((time.time(), valores))

    def parar(self):
        subprocess.run(['docker', 'rm', '-f', AMOSTRADOR_DO_BANCO], capture_output=True)

    def na_janela(self, inicio, fim, requisicoes):
        """Fração do tempo executando consultas (% de um núcleo) e linhas e blocos por requisição."""
        with self.trava:
            amostras = [a for a in self.amostras if inicio <= a[0] <= fim]
        if len(amostras) < 2:
            return {}
        (t0, a), (t1, b) = amostras[0], amostras[-1]
        escala = (fim - inicio) / (t1 - t0)  # as amostras cobrem quase toda a janela
        por_req = max(requisicoes, 1)
        return {
            'banco_execucao_pct': (b[1] - a[1]) / ((t1 - t0) * 1000) * 100,
            'banco_linhas_por_req': (b[2] - a[2]) * escala / por_req,
            'banco_blocos_por_req': (b[3] + b[4] - a[3] - a[4]) * escala / por_req,
        }


class MonitorDoCache(threading.Thread):
    """Lê as estatísticas do Redis a cada segundo, para a taxa de acerto ao longo do tempo."""

    def __init__(self, api):
        super().__init__(daemon=True)
        self.api = api
        self.leituras = []
        self.parar = threading.Event()

    def run(self):
        while not self.parar.is_set():
            try:
                dado = self.api.chamar('GET', '/api/laboratorio/cache', timeout=5)
                self.leituras.append((time.time(), dado['acertos'], dado['falhas'], dado['chaves'],
                                      dado['chaves_expiradas_pelo_ttl']))
            except OSError:
                pass
            self.parar.wait(1)


# --------------------------------------------------------------------------- k6

def comando_do_k6(args, script, variaveis, ambiente_do_k6):
    if args.k6 == 'docker':
        # sem --rm: o contêiner é removido depois que o id dele é lido (para a CPU do k6)
        comando = ['docker', 'compose', 'run', '--name', CONTEINERES['k6']]
        for nome, valor in ambiente_do_k6.items():
            comando += ['-e', f'{nome}={valor}']
        comando += ['k6', 'run', '--quiet']
        alvo = f'k6/{script}'
    else:
        comando = ['k6', 'run', '--quiet', '-e', f'BASE_URL={args.api}']
        alvo = str(PASTA / 'k6' / script)
    for nome, valor in variaveis.items():
        comando += ['-e', f'{nome}={valor}']
    return comando + [alvo]


def rodar_k6(args, script, variaveis, log, ambiente_do_k6=None):
    """Roda o k6. Devolve o código de saída (0 = ok; 99 = algum limite estourado) e o id do
    contêiner do k6 (12 caracteres), quando ele roda no Docker.

    ambiente_do_k6: variáveis do próprio k6 (não do script), como as do painel web."""
    ambiente_do_k6 = {'K6_NO_USAGE_REPORT': 'true', **(ambiente_do_k6 or {})}
    if args.k6 == 'docker':
        subprocess.run(['docker', 'rm', '-f', CONTEINERES['k6']], capture_output=True)
    ambiente = {**os.environ, **ambiente_do_k6}
    processo = subprocess.Popen(comando_do_k6(args, script, variaveis, ambiente_do_k6), cwd=RAIZ, env=ambiente,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding='utf-8', errors='replace')
    for linha in processo.stdout:
        if not linha.startswith(' Container biblioteca-k6'):
            print(linha, end='')
        log.write(linha)
    codigo = processo.wait()
    identificador = None
    if args.k6 == 'docker':
        identificador = (saida_de(['docker', 'inspect', '-f', '{{.Id}}', CONTEINERES['k6']]) or '')[:12] or None
        subprocess.run(['docker', 'rm', '-f', CONTEINERES['k6']], capture_output=True)
    return codigo, identificador


def caminho_da_saida(args, pasta, nome, pasta_destino='k6', extensao='json'):
    """Caminho do arquivo nesta máquina e o mesmo caminho como o k6 o enxerga."""
    arquivo = pasta / pasta_destino / f'{nome}.{extensao}'
    if args.k6 == 'docker':  # visto de dentro do contêiner do k6, que monta a pasta testes-carga
        return arquivo, arquivo.relative_to(PASTA).as_posix()
    return arquivo, str(arquivo)


# --------------------------------------------------------------------------- ambiente

def nome_do_processador():
    if sys.platform == 'win32':
        try:
            import winreg
            chave = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
            return winreg.QueryValueEx(chave, 'ProcessorNameString')[0].strip()
        except OSError:
            pass
    return platform.processor()


def memoria_total_gb():
    if sys.platform == 'win32':
        import ctypes

        class Estado(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

        estado = Estado()
        estado.dwLength = ctypes.sizeof(Estado)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
        return round(estado.ullTotalPhys / 2 ** 30, 1)
    if Path('/proc/meminfo').exists():
        return round(int(Path('/proc/meminfo').read_text().split()[1]) / 2 ** 20, 1)
    return None


def registrar_ambiente(args, api, pasta):
    if args.k6 == 'docker':
        versao_k6 = saida_de(['docker', 'compose', 'run', '--rm', 'k6', 'version'], cwd=RAIZ)
    else:
        versao_k6 = saida_de(['k6', 'version'])
    ambiente = {
        'data': datetime.now().isoformat(timespec='seconds'),
        'parametros': {chave: valor for chave, valor in vars(args).items()},
        'maquina': {
            'sistema': platform.platform(),
            'processador': nome_do_processador(),
            'nucleos_logicos': os.cpu_count(),
            'memoria_gb': memoria_total_gb(),
        },
        'docker': saida_de(['docker', 'info', '--format',
                            '{{.ServerVersion}} | VM com {{.NCPU}} CPUs e {{.MemTotal}} bytes de memória']),
        'k6': (versao_k6 or '').splitlines()[-1:] or None,
        'python_do_roteiro': platform.python_version(),
        'conteineres_em_execucao': (saida_de(['docker', 'ps', '--format', '{{.Names}} ({{.Image}})']) or '').splitlines(),
        'api': api.chamar('GET', '/api/laboratorio/estado'),
        'ida_e_volta_ao_banco': api.chamar('GET', '/api/laboratorio/banco/ida-e-volta?vezes=50'),
    }
    (pasta / 'ambiente.json').write_text(json.dumps(ambiente, ensure_ascii=False, indent=2), encoding='utf-8')
    return ambiente


# --------------------------------------------------------------------------- execução

def argumentos():
    parser = argparse.ArgumentParser(description='Testes de desempenho da biblioteca (item 3 do trabalho).')
    parser.add_argument('--api', default='http://localhost:8000', help='endereço da API, visto desta máquina')
    parser.add_argument('--cenarios', default='cache,persistencia,indice,ttl',
                        help='cenários, separados por vírgula: cache, persistencia, indice e ttl')
    parser.add_argument('--cargas', default='10,50,100,200', help='níveis de carga, em usuários virtuais')
    parser.add_argument('--repeticoes', type=int, default=3)
    parser.add_argument('--aquecimento', type=int, default=10, help='segundos de aquecimento por nível')
    parser.add_argument('--duracao', type=int, default=30, help='segundos de medição por nível')
    parser.add_argument('--ttls', default=','.join(map(str, [5, 30, 120, 600])),
                        help='TTLs (s) do experimento do TTL')
    parser.add_argument('--carga-ttl', type=int, default=50, help='VUs do experimento do TTL')
    parser.add_argument('--duracao-ttl', type=int, default=60, help='segundos de medição do experimento do TTL')
    parser.add_argument('--descanso', type=int, default=5, help='segundos de pausa entre execuções')
    parser.add_argument('--k6', choices=['docker', 'local'], default='docker',
                        help='docker: k6 num contêiner na rede da API (padrão); local: k6 instalado aqui')
    parser.add_argument('--sem-html', dest='html', action='store_false',
                        help='não gravar o relatório HTML do painel web do k6 (1ª repetição de cada versão)')
    parser.add_argument('--rapido', action='store_true',
                        help='conferência do roteiro: cargas 10 e 50, tempos curtos, uma repetição')
    parser.add_argument('--minutos', type=float,
                        help='para antes de começar uma execução que terminaria depois deste tempo')
    parser.add_argument('--continuar', metavar='PASTA',
                        help='retoma a matriz da pasta indicada, com os parâmetros dela, pulando as '
                             'execuções que já estão em execucoes.csv')
    args = parser.parse_args()
    if args.continuar:  # os parâmetros da matriz são os da primeira parte, gravados no ambiente
        pasta = Path(args.continuar).resolve()
        originais = json.loads((pasta / 'ambiente.json').read_text(encoding='utf-8'))['parametros']
        for nome, valor in originais.items():
            if nome not in ('continuar', 'minutos', 'api'):
                setattr(args, nome, valor)
    elif args.rapido:
        args.cargas, args.repeticoes, args.aquecimento, args.duracao = '10,50', 1, 3, 5
        args.ttls, args.duracao_ttl, args.descanso, args.html = '5,600', 15, 2, False
    return args


def montar_plano(args):
    cenarios = [c.strip() for c in args.cenarios.split(',') if c.strip()]
    desconhecidos = set(cenarios) - set(SCRIPTS)
    if desconhecidos:
        raise SystemExit(f'Cenários desconhecidos: {", ".join(sorted(desconhecidos))}')
    plano = []
    for repeticao in range(1, args.repeticoes + 1):
        for cenario in cenarios:
            if cenario == 'ttl':
                continue
            versoes = VERSOES[cenario]
            deslocamento = (repeticao - 1) % len(versoes)  # alterna a ordem a cada repetição
            for versao in versoes[deslocamento:] + versoes[:deslocamento]:
                plano.append((cenario, versao, repeticao, None))
    if 'ttl' in cenarios:  # bloco à parte: cada TTL exige recriar o contêiner da API
        for repeticao in range(1, args.repeticoes + 1):
            for ttl in (int(t) for t in args.ttls.split(',')):
                plano.append(('ttl', 'com-cache-frio', repeticao, ttl))
    return plano


def segundos_estimados(args, cenario):
    """Duração prevista de uma execução, com o preparo, a recriação da API, a partida do contêiner
    do k6 e o descanso (medidas: cerca de 4 minutos por execução da matriz completa)."""
    if cenario == 'ttl':
        return 5 + 3 + args.duracao_ttl + 3 + 20 + args.descanso + 40
    niveis = len(args.cargas.split(','))
    return niveis * (args.aquecimento + args.duracao + 3) + 8 + args.descanso + 40


def tempo_estimado(args, plano):
    return sum(segundos_estimados(args, cenario) for cenario, *_ in plano) / 60


def chave_da_execucao(cenario, versao, repeticao, ttl):
    """Identifica uma execução como ela aparece em execucoes.csv."""
    return cenario, versao, str(repeticao), str(ttl) if ttl else ''


def execucoes_gravadas(pasta):
    arquivo = pasta / 'execucoes.csv'
    if not arquivo.exists():
        return set()
    with open(arquivo, encoding='utf-8') as entrada:
        return {(l['cenario'], l['versao'], l['repeticao'], l['ttl_s']) for l in csv.DictReader(entrada)}


def aquecer_tudo(args, plano, log):
    """Uma passada curta por todas as versões, antes da primeira medição."""
    print('Aquecimento geral (resultados descartados)...')
    feitas = set()
    for cenario, versao, _, _ in plano:
        if cenario == 'ttl' or (cenario, versao) in feitas:
            continue
        feitas.add((cenario, versao))
        rodar_k6(args, SCRIPTS[cenario], {'VERSAO': versao, 'CARGAS': '50', 'AQUECIMENTO': '0',
                                          'DURACAO': '3' if args.rapido else '5'}, log)


def diferenca_do_banco(antes, depois):
    """Comandos SQL executados entre duas leituras de /api/laboratorio/banco/estatisticas."""
    anteriores = {c['id']: c for c in antes['comandos']}
    comandos = []
    for comando in depois['comandos']:
        anterior = anteriores.get(comando['id'], {})
        execucoes = comando['execucoes'] - anterior.get('execucoes', 0)
        if execucoes <= 0:
            continue
        comandos.append({
            'execucoes': execucoes,
            'tempo_total_ms': comando['tempo_total_ms'] - anterior.get('tempo_total_ms', 0),
            'linhas': comando['linhas'] - anterior.get('linhas', 0),
            'blocos_em_memoria': comando['blocos_em_memoria'] - anterior.get('blocos_em_memoria', 0),
            'blocos_do_disco': comando['blocos_do_disco'] - anterior.get('blocos_do_disco', 0),
            'comando': comando['comando'],
        })
    comandos.sort(key=lambda c: c['tempo_total_ms'], reverse=True)
    total = {chave: depois['total'][chave] - antes['total'][chave] for chave in depois['total']}
    return {'total': total, 'comandos': comandos[:10]}


def medir(args, api, amostrador, amostrador_do_banco, pasta, cenario, versao, repeticao, ttl, log, escritor):
    nome = f'{cenario}_{versao}' + (f'_ttl{ttl}' if ttl else '') + f'_r{repeticao}'
    arquivo, saida = caminho_da_saida(args, pasta, nome)
    if ttl:
        variaveis = {'VERSAO': versao, 'CARGAS': str(args.carga_ttl), 'AQUECIMENTO': '5',
                     'DURACAO': str(args.duracao_ttl)}
    else:
        variaveis = {'VERSAO': versao, 'CARGAS': args.cargas, 'AQUECIMENTO': str(args.aquecimento),
                     'DURACAO': str(args.duracao)}
    variaveis['SAIDA'] = saida

    # relatório HTML do painel web do k6, na primeira repetição de cada versão
    painel = {}
    if args.html and repeticao == 1:
        relatorio, relatorio_k6 = caminho_da_saida(args, pasta, nome, pasta_destino='html', extensao='html')
        painel = {'K6_WEB_DASHBOARD': 'true', 'K6_WEB_DASHBOARD_EXPORT': relatorio_k6,
                  'K6_WEB_DASHBOARD_PERIOD': '2s'}

    estatisticas_antes = api.chamar('GET', '/api/laboratorio/banco/estatisticas?limite=1000')
    monitor = MonitorDoCache(api) if cenario in ('cache', 'ttl') and versao != 'sem-cache' else None
    if monitor:
        monitor.start()
    codigo, id_do_k6 = rodar_k6(args, SCRIPTS[cenario], variaveis, log, painel)
    if monitor:
        monitor.parar.set()
        monitor.join()
    if codigo not in (0, 99) or not arquivo.exists():
        print(f'  ERRO: o k6 terminou com código {codigo} em {nome}; execução ignorada.')
        return

    # Os ids dos contêineres são lidos antes de a API poder ser recriada logo abaixo: a CPU da
    # medição é a do contêiner que atendeu o k6, não a do que o substitui.
    ids = ids_dos_conteineres()
    if id_do_k6:
        ids[CONTEINERES['k6']] = id_do_k6
    resumo = json.loads(arquivo.read_text(encoding='utf-8'))
    try:
        estatisticas_depois = api.chamar('GET', '/api/laboratorio/banco/estatisticas?limite=1000', timeout=30)
    except OSError:
        # Depois de uma carga alta no LAZY, a API ainda tem na fila as requisições que o k6
        # abandonou, e cada uma ocupa uma conexão com o banco por vários segundos. A API é
        # recriada, o que descarta essa fila, e a leitura é refeita; o que o banco executou para
        # essas requisições até ali entra na conta da execução.
        print('  a API ainda atende requisições abandonadas pelo k6; recriando-a para ler o banco')
        reiniciar_api(api, ttl or TTL_PADRAO)
        estatisticas_depois = api.chamar('GET', '/api/laboratorio/banco/estatisticas?limite=1000')
        # As conexões da API derrubada estavam no meio de consultas, e o pooler do Supabase leva
        # uns 20 s para liberá-las; sem esta pausa, a execução seguinte espera por conexão.
        time.sleep(30)
    (pasta / 'banco' / f'{nome}.json').write_text(
        json.dumps(diferenca_do_banco(estatisticas_antes, estatisticas_depois), ensure_ascii=False, indent=2),
        encoding='utf-8')
    if monitor:
        with open(pasta / 'cache' / f'{nome}.csv', 'w', newline='', encoding='utf-8') as saida_cache:
            gravador = csv.writer(saida_cache)
            gravador.writerow(['t', 'acertos', 'falhas', 'chaves', 'expiradas'])
            gravador.writerows(monitor.leituras)

    inicio = resumo['preparo']['inicio_dos_cenarios_ms'] / 1000
    for janela, nivel in zip(resumo['janelas'], resumo['niveis']):
        amostras = amostrador.na_janela(inicio + janela['inicio_s'], inicio + janela['fim_s'])
        lat = nivel['latencia_ms']
        linha = {
            'cenario': cenario, 'versao': versao, 'ttl_s': ttl or '', 'repeticao': repeticao,
            'vus': nivel['vus'], 'requisicoes': nivel['requisicoes'], 'vazao_rps': nivel['vazao_rps'],
            'latencia_media_ms': lat['media'], 'latencia_mediana_ms': lat['mediana'],
            'latencia_p90_ms': lat['p90'], 'latencia_p95_ms': lat['p95'], 'latencia_p99_ms': lat['p99'],
            'latencia_max_ms': lat['maxima'], 'taxa_de_erros': nivel['taxa_de_erros'],
            'consultas_sql_por_req': nivel['consultas_sql_por_requisicao'],
            'tempo_no_banco_ms': nivel['tempo_no_banco_ms'], 'tempo_no_servidor_ms': nivel['tempo_no_servidor_ms'],
            'taxa_de_acerto_cache': nivel['taxa_de_acerto_do_cache'],
            'kb_por_req': (nivel['bytes_recebidos'] or 0) / max(nivel['requisicoes'], 1) / 1024,
            'limites_ok': all(nivel['limites'].values()),
            'arquivo': arquivo.name,
            **recursos(amostras, ids),
            **amostrador_do_banco.na_janela(inicio + janela['inicio_s'], inicio + janela['fim_s'],
                                            nivel['requisicoes']),
        }
        escritor.writerow({coluna: _formatar(linha.get(coluna)) for coluna in COLUNAS})


def _formatar(valor):
    if valor is None:
        return ''
    if isinstance(valor, float):
        return f'{valor:.4f}'
    return valor


def registrar_retomada(api, pasta):
    """Na retomada, acrescenta ao ambiente.json quando a matriz continuou e a ida e volta medida."""
    arquivo = pasta / 'ambiente.json'
    ambiente = json.loads(arquivo.read_text(encoding='utf-8'))
    ambiente.setdefault('retomadas', []).append({
        'data': datetime.now().isoformat(timespec='seconds'),
        'conteineres_em_execucao': (saida_de(['docker', 'ps', '--format', '{{.Names}} ({{.Image}})']) or '').splitlines(),
        'ida_e_volta_ao_banco': api.chamar('GET', '/api/laboratorio/banco/ida-e-volta?vezes=20'),
    })
    arquivo.write_text(json.dumps(ambiente, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    inicio = time.time()
    args = argumentos()
    api = Api(args.api)
    if not api.no_ar():
        raise SystemExit(f'A API não está respondendo em {args.api}. Suba tudo com: docker compose up -d --build')

    plano = montar_plano(args)
    if args.continuar:
        pasta = Path(args.continuar).resolve()
    else:
        sessao = datetime.now().strftime('%Y-%m-%d_%Hh%M') + ('-rapido' if args.rapido else '')
        pasta = PASTA / 'resultados' / sessao
    for subpasta in ('k6', 'banco', 'cache', 'html'):
        (pasta / subpasta).mkdir(parents=True, exist_ok=True)
    feitas = execucoes_gravadas(pasta)
    pendentes = [(numero, item) for numero, item in enumerate(plano, 1)
                 if chave_da_execucao(*item) not in feitas]

    print(f'{len(pendentes)} de {len(plano)} execuções do k6 por fazer, cerca de '
          f'{tempo_estimado(args, [item for _, item in pendentes]):.0f} minutos.')
    print(f'Resultados em {pasta.relative_to(RAIZ)}')
    # API recém-criada: uma parte anterior interrompida pode ter deixado requisições na fila
    reiniciar_api(api, TTL_PADRAO)
    print(f'Carregando o banco na memória: {api.chamar("POST", "/api/laboratorio/banco/aquecer")}')
    if args.continuar:
        registrar_retomada(api, pasta)
    else:
        registrar_ambiente(args, api, pasta)

    amostrador = Amostrador()
    amostrador.iniciar()
    amostrador_do_banco = AmostradorDoBanco()
    amostrador_do_banco.iniciar()
    ttl_atual = api.chamar('GET', '/api/laboratorio/estado')['configuracao']['cache_ttl_segundos']
    arquivo_de_execucoes = pasta / 'execucoes.csv'
    com_cabecalho = arquivo_de_execucoes.exists() and arquivo_de_execucoes.stat().st_size > 0
    with open(pasta / 'execucao.log', 'a', encoding='utf-8') as log, \
            open(arquivo_de_execucoes, 'a', newline='', encoding='utf-8') as arquivo_csv:
        escritor = csv.DictWriter(arquivo_csv, fieldnames=COLUNAS)
        if not com_cabecalho:
            escritor.writeheader()
        try:
            if not args.continuar:
                aquecer_tudo(args, plano, log)
            feitas_nesta_parte = 0
            for numero, (cenario, versao, repeticao, ttl) in pendentes:
                if (args.minutos and feitas_nesta_parte
                        and time.time() - inicio + segundos_estimados(args, cenario) > args.minutos * 60):
                    break
                feitas_nesta_parte += 1
                decorrido = (time.time() - inicio) / 60
                print(f'\n[{numero}/{len(plano)}] {cenario} / {versao}'
                      + (f' / TTL {ttl} s' if ttl else '') + f' / repetição {repeticao}'
                      + f'  ({decorrido:.0f} min decorridos)')
                ttl_atual = ttl if cenario == 'ttl' else TTL_PADRAO
                reiniciar_api(api, ttl_atual)
                medir(args, api, amostrador, amostrador_do_banco, pasta, cenario, versao, repeticao, ttl,
                      log, escritor)
                arquivo_csv.flush()
                time.sleep(args.descanso)
        finally:
            amostrador.parar()
            amostrador_do_banco.parar()
            if ttl_atual != TTL_PADRAO:
                print(f'Voltando a API ao TTL padrão ({TTL_PADRAO} s)...')
                reiniciar_api(api, TTL_PADRAO)
            try:
                api.chamar('DELETE', '/api/laboratorio/indices/leitor-data')
            except OSError:
                pass

    faltam = len(plano) - len(execucoes_gravadas(pasta) & {chave_da_execucao(*item) for item in plano})
    if faltam:
        print(f'\nParte concluída em {(time.time() - inicio) / 60:.0f} minutos; faltam {faltam} execuções. '
              f'Para continuar:\n    python testes-carga/executar.py --continuar '
              f'{pasta.relative_to(RAIZ).as_posix()}' + (f' --minutos {args.minutos:g}' if args.minutos else ''))
        return
    print(f'\nMatriz completa ({(time.time() - inicio) / 60:.0f} minutos nesta parte). '
          'Gerando tabelas e gráficos...')
    subprocess.run([sys.executable, str(PASTA / 'analisar.py'), str(pasta)], check=False)


if __name__ == '__main__':
    main()

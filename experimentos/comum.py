"""Funções comuns aos experimentos dos itens 1 e 2. Só usa a biblioteca padrão."""

import http.client
import json
import os
import re
import socket
import statistics
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = Path(__file__).resolve().parent / 'resultados'
API = os.environ.get('API', 'http://localhost:8000')


class Resposta:
    def __init__(self, status, cabecalhos, corpo, tempo_ms):
        self.status = status
        self.cabecalhos = cabecalhos
        self.corpo = corpo
        self.tempo_ms = tempo_ms  # medido aqui, no cliente

    def json(self):
        return json.loads(self.corpo)

    def cabecalho(self, nome, padrao=None):
        return self.cabecalhos.get(nome.lower(), padrao)

    @property
    def consultas_sql(self):
        return int(self.cabecalho('x-consultas-sql', '0'))

    def _tempo(self, nome):
        achado = re.search(rf'{nome};dur=([\d.]+)', self.cabecalho('server-timing', ''))
        return float(achado.group(1)) if achado else None

    @property
    def tempo_no_servidor_ms(self):
        return self._tempo('total')

    @property
    def tempo_no_banco_ms(self):
        return self._tempo('banco')


class _Conexao(http.client.HTTPConnection):
    """Envia cabeçalho e corpo da requisição num único pacote.

    O http.client manda os dois em envios separados. Numa conexão persistente, o corpo ficava
    esperando o ACK atrasado do outro lado (uns 40 ms) antes de seguir, e cada PUT parecia 40 ms
    mais lento do que era. O curl e o k6 já mandam tudo junto."""

    def _send_output(self, message_body=None, encode_chunked=False):
        if isinstance(message_body, bytes):
            self._buffer.extend((b'', b''))
            mensagem = b'\r\n'.join(self._buffer) + message_body
            del self._buffer[:]
            self.send(mensagem)
        else:
            super()._send_output(message_body, encode_chunked)


class Cliente:
    """Cliente HTTP com uma conexão persistente, para não medir a abertura de conexões."""

    def __init__(self, base=API):
        partes = urlsplit(base)
        self.host, self.porta = partes.hostname, partes.port or 80
        self.conexao = None

    def requisitar(self, metodo, caminho, corpo=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        cabecalhos = {'Content-Type': 'application/json'} if dados else {}
        for tentativa in range(2):
            if self.conexao is None:
                self.conexao = _Conexao(self.host, self.porta, timeout=300)
                self.conexao.connect()
                self.conexao.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                inicio = time.perf_counter()
                self.conexao.request(metodo, caminho, body=dados, headers=cabecalhos)
                resposta = self.conexao.getresponse()
                conteudo = resposta.read()
                tempo = (time.perf_counter() - inicio) * 1000
                return Resposta(resposta.status, {k.lower(): v for k, v in resposta.getheaders()},
                                conteudo, tempo)
            except (http.client.HTTPException, OSError):
                self.conexao.close()
                self.conexao = None
                if tentativa:
                    raise
        raise RuntimeError('inalcançável')

    def get(self, caminho):
        return self.requisitar('GET', caminho)

    def json(self, metodo, caminho, corpo=None):
        resposta = self.requisitar(metodo, caminho, corpo)
        if resposta.status >= 300:
            raise RuntimeError(f'{metodo} {caminho} respondeu {resposta.status}: {resposta.corpo[:300]!r}')
        return resposta.json()


def esperar_api(cliente, limite=120):
    fim = time.time() + limite
    while time.time() < fim:
        try:
            if cliente.get('/api/saude').status == 200:
                return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f'A API não respondeu em {API}. Suba tudo com: docker compose up -d --build')


def recriar_api(cliente, ttl):
    """Recria o contêiner da API com outro TTL de cache e espera ela voltar."""
    ambiente = {**os.environ, 'CACHE_TTL_SEGUNDOS': str(ttl)}
    subprocess.run(['docker', 'compose', 'up', '-d', 'api'], cwd=RAIZ, env=ambiente, check=True,
                   capture_output=True)
    time.sleep(2)
    cliente.conexao = None
    esperar_api(cliente)


def sql_no_banco(comando):
    """Executa SQL direto no PostgreSQL, por fora da API (psql dentro do contêiner do banco)."""
    resultado = subprocess.run(
        ['docker', 'exec', '-i', 'biblioteca-banco', 'psql', '-U', 'biblioteca', '-d', 'biblioteca',
         '-v', 'ON_ERROR_STOP=1', '-At'],
        input=comando, capture_output=True, text=True, encoding='utf-8', check=True)
    return resultado.stdout.strip()


def literal(texto):
    return "'" + texto.replace("'", "''") + "'"


def mediana(valores):
    valores = [v for v in valores if v is not None]
    return statistics.median(valores) if valores else None


def percentil(valores, p):
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    posicao = (len(valores) - 1) * p
    baixo = int(posicao)
    alto = min(baixo + 1, len(valores) - 1)
    return valores[baixo] + (valores[alto] - valores[baixo]) * (posicao - baixo)


def br(valor, casas=0):
    if valor is None:
        return '–'
    texto = f'{valor:,.{casas}f}'
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def tabela(cabecalho, linhas, alinhamento=None):
    """Tabela em Markdown. alinhamento: string com 'e' (esquerda) ou 'd' (direita) por coluna."""
    alinhamento = alinhamento or 'e' + 'd' * (len(cabecalho) - 1)
    separador = '|' + '|'.join('---' if a == 'e' else '---:' for a in alinhamento) + '|'
    texto = ['| ' + ' | '.join(cabecalho) + ' |', separador]
    texto += ['| ' + ' | '.join(str(c) for c in linha) + ' |' for linha in linhas]
    return '\n'.join(texto)


def gravar(nome, conteudo):
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    caminho = RESULTADOS / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(conteudo, str):
        conteudo = json.dumps(conteudo, ensure_ascii=False, indent=2, default=str)
    caminho.write_text(conteudo + '\n', encoding='utf-8')
    return caminho

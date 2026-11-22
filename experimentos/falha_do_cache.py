"""Extra do item 1 (seção 3.6 do README): a ficha com cache quando o Redis cai.

O cache é um atalho, não a fonte dos dados: se o Redis não responde, a ficha vem do banco
(X-Cache: INDISPONIVEL) e a requisição não falha. O roteiro tira o Redis do ar de dois jeitos:

  A. parado (docker compose stop cache). A primeira leitura espera a falha aparecer; as
     seguintes vão direto ao banco, enquanto a vigia da API testa o Redis em segundo plano. Um
     PUT feito nesse intervalo deixa a invalidação pendente. Quando o Redis volta (vazio: ele não
     grava nada em disco), a ficha volta a ser guardada: MISS e depois HIT.
  B. travado (docker compose pause cache): o processo do Redis congela com os dados na memória e
     para de responder, sem fechar as conexões. Um PUT nesse intervalo deixa a invalidação
     pendente; quando o Redis volta (unpause), a vigia apaga a ficha antiga antes de o cache voltar
     a ser usado, e a leitura seguinte é MISS com o título novo, e não HIT com o antigo.

Uma conexão só com a API, sem ficar parada mais que 5 s (o keep-alive do uvicorn): as leituras
caem no mesmo processo da API, e cada processo tem a sua vigia. O livro, o Redis e o cache voltam
ao estado inicial no fim.

    python experimentos/falha_do_cache.py      (com a API no ar: docker compose up -d)
"""

import subprocess
import time

from comum import RAIZ, Cliente, br, esperar_api, gravar, hora, literal, mediana, sql_no_banco, tabela

LIVRO = 42
COM_CACHE = f'/api/livros/{LIVRO}/com-cache'
SEM_CACHE = f'/api/livros/{LIVRO}/sem-cache'
LEITURAS = 10      # leituras seguidas com o Redis parado (e sem cache, para comparar)
TRAVADO_S = 10     # quanto tempo o Redis fica congelado na parte B
INTERVALO_S = 0.5  # entre as leituras que mantêm a conexão viva e esperam o cache voltar


def compose(*argumentos, verificar=True):
    """docker compose na pasta do projeto; devolve a duração em segundos."""
    inicio = time.perf_counter()
    subprocess.run(['docker', 'compose', *argumentos], cwd=RAIZ, check=verificar, capture_output=True)
    return time.perf_counter() - inicio


def esperar_redis_saudavel(limite=60):
    fim = time.time() + limite
    while time.time() < fim:
        saude = subprocess.run(['docker', 'inspect', '-f', '{{.State.Health.Status}}', 'biblioteca-cache'],
                               capture_output=True, text=True).stdout.strip()
        if saude == 'healthy':
            return
        time.sleep(1)
    raise SystemExit('O contêiner do Redis não ficou saudável a tempo.')


def leituras(n):
    return f'{n} leitura' if n == 1 else f'{n} leituras'


def cabecalho_do_cache(r):
    if r.cabecalho('x-cache'):
        return r.cabecalho('x-cache')
    if r.cabecalho('x-cache-invalidado'):
        return f"invalidado: {r.cabecalho('x-cache-invalidado')}"
    return '–'


class Registro:
    """As linhas de uma parte do experimento, com o tempo contado a partir da queda do Redis."""

    def __init__(self, parte):
        self.parte = parte
        self.linhas = []
        self.zero = time.perf_counter()

    def zerar_relogio(self):
        self.zero = time.perf_counter()

    def agora(self):
        return time.perf_counter() - self.zero

    def _anotar(self, linha):
        linha = {'parte': self.parte, 't_s': round(self.agora(), 2), **linha}
        self.linhas.append(linha)
        tempo = '' if linha['tempo_no_servidor_ms'] is None else f"{linha['tempo_no_servidor_ms']:8.2f} ms"
        print(f"  {linha['passo']:>6} {linha['t_s']:6.1f}s  {linha['operacao']:<34} {linha['status']!s:>3} "
              f"{linha['cache']:<20} {tempo}  {linha['titulo'][:60]}")
        return linha

    def resposta(self, passo, operacao, r, observacao=''):
        corpo = r.json() if r.status == 200 else {}
        return self._anotar({
            'passo': passo, 'operacao': operacao, 'status': r.status, 'cache': cabecalho_do_cache(r),
            'consultas_sql': r.consultas_sql, 'tempo_no_servidor_ms': r.tempo_no_servidor_ms,
            'tempo_no_cliente_ms': round(r.tempo_ms, 2), 'titulo': corpo.get('titulo', '–'),
            'gerada_em': hora(corpo['gerada_em']) if 'gerada_em' in corpo else '–',
            'observacao': observacao,
        })

    def evento(self, passo, operacao, observacao):
        return self._anotar({
            'passo': passo, 'operacao': operacao, 'status': '–', 'cache': '–', 'consultas_sql': None,
            'tempo_no_servidor_ms': None, 'tempo_no_cliente_ms': None, 'titulo': '–', 'gerada_em': '–',
            'observacao': observacao,
        })


def ler_ate_o_cache_voltar(cliente, limite_s):
    """Lê com cache a cada INTERVALO_S até a resposta deixar de ser INDISPONIVEL. Devolve a primeira
    resposta com o cache de volta e quantas leituras ainda vieram do banco antes dela."""
    fim = time.perf_counter() + limite_s
    vindas_do_banco = 0
    while time.perf_counter() < fim:
        r = cliente.get(COM_CACHE)
        if r.cabecalho('x-cache') != 'INDISPONIVEL':
            return r, vindas_do_banco
        vindas_do_banco += 1
        time.sleep(INTERVALO_S)
    raise SystemExit(f'O cache não voltou a ser usado em {limite_s} s.')


def parte_a(cliente, titulo_original):
    print('A. Redis parado (docker compose stop cache):')
    reg = Registro('A')
    cliente.json('DELETE', '/api/laboratorio/cache')
    reg.resposta('A1', 'GET com cache, Redis no ar', cliente.get(COM_CACHE), 'falha: monta a ficha no banco e guarda')
    reg.resposta('A2', 'GET com cache de novo', cliente.get(COM_CACHE), 'acerto: nenhuma consulta ao banco')

    duracao = compose('stop', 'cache')
    reg.zerar_relogio()
    reg.evento('A3', 'docker compose stop cache', f'o contêiner do Redis parou ({br(duracao, 1)} s)')
    for i in range(1, LEITURAS + 1):
        reg.resposta(f'A4.{i}', 'GET com cache, Redis parado', cliente.get(COM_CACHE),
                     'espera a falha aparecer e vai ao banco' if i == 1 else 'direto ao banco, sem tentar o Redis')
    for i in range(1, LEITURAS + 1):
        reg.resposta(f'A5.{i}', 'GET sem cache, para comparar', cliente.get(SEM_CACHE), 'sempre do banco')

    titulo_novo = f'{titulo_original} (alterado com o Redis parado)'
    reg.resposta('A6', 'PUT /api/livros/{id} (novo título)',
                 cliente.requisitar('PUT', f'/api/livros/{LIVRO}', {'titulo': titulo_novo}),
                 'a alteração vale; a invalidação fica pendente')
    reg.resposta('A7', 'GET com cache, Redis parado', cliente.get(COM_CACHE), 'já com o título novo, do banco')

    duracao = compose('start', 'cache')
    inicio = time.perf_counter()
    reg.evento('A8', 'docker compose start cache', f'o contêiner do Redis subiu de novo, vazio ({br(duracao, 1)} s)')
    r, vindas_do_banco = ler_ate_o_cache_voltar(cliente, limite_s=60)
    reg.resposta('A9', 'GET com cache, Redis de volta', r,
                 f'o cache voltou {br(time.perf_counter() - inicio, 1)} s depois do start '
                 f'({leituras(vindas_do_banco)} ainda do banco antes)')
    reg.resposta('A10', 'GET com cache de novo', cliente.get(COM_CACHE), 'acerto: o cache voltou ao normal')
    return reg.linhas, titulo_novo


def parte_b(cliente, titulo_original, titulo_antigo):
    print(f'B. Redis travado por {TRAVADO_S} s (docker compose pause cache), com os dados ainda lá:')
    reg = Registro('B')
    reg.resposta('B1', 'GET com cache, Redis no ar', cliente.get(COM_CACHE), 'a ficha está no cache')

    duracao = compose('pause', 'cache')
    reg.zerar_relogio()
    reg.evento('B2', 'docker compose pause cache',
               f'o Redis congela: as conexões continuam abertas, sem resposta ({br(duracao, 1)} s)')
    reg.resposta('B3', 'GET com cache, Redis travado', cliente.get(COM_CACHE), 'espera o tempo limite e vai ao banco')
    titulo_novo = f'{titulo_original} (alterado com o Redis travado)'
    reg.resposta('B4', 'PUT /api/livros/{id} (novo título)',
                 cliente.requisitar('PUT', f'/api/livros/{LIVRO}', {'titulo': titulo_novo}),
                 'a alteração vale; a invalidação fica pendente')
    i = 0
    while reg.agora() < TRAVADO_S:  # leituras enquanto o Redis está travado (mantêm a conexão viva)
        i += 1
        reg.resposta(f'B5.{i}', 'GET com cache, Redis travado', cliente.get(COM_CACHE),
                     'título novo, do banco, sem tentar o Redis')
        time.sleep(INTERVALO_S)

    duracao = compose('unpause', 'cache')
    inicio = time.perf_counter()
    reg.evento('B6', 'docker compose unpause cache', f'o Redis volta, com a ficha antiga na memória ({br(duracao, 1)} s)')
    r, vindas_do_banco = ler_ate_o_cache_voltar(cliente, limite_s=30)
    titulo = r.json()['titulo']
    if r.cabecalho('x-cache') == 'MISS' and titulo == titulo_novo:
        conclusao = 'MISS com o título novo: a ficha antiga foi apagada antes de o cache voltar'
    elif titulo == titulo_antigo:
        conclusao = 'ATENÇÃO: voltou a ficha antiga (a invalidação pendente não foi feita)'
    else:
        conclusao = f"resultado inesperado: X-Cache {r.cabecalho('x-cache')}"
    reg.resposta('B7', 'GET com cache, Redis de volta', r,
                 f'{conclusao}; {br(time.perf_counter() - inicio, 1)} s depois do unpause '
                 f'({leituras(vindas_do_banco)} ainda do banco antes)')
    reg.resposta('B8', 'GET com cache de novo', cliente.get(COM_CACHE), 'acerto, com o título novo')
    return reg.linhas, conclusao


def agrupar(linhas, passo, observacao):
    """Uma linha da tabela em Markdown para várias leituras iguais: mediana do tempo no servidor."""
    return {
        'passo': passo, 't_s': f"{br(linhas[0]['t_s'], 1)} a {br(linhas[-1]['t_s'], 1)}",
        'operacao': linhas[0]['operacao'],
        'status': ', '.join(sorted({str(l['status']) for l in linhas})),
        'cache': ', '.join(sorted({l['cache'] for l in linhas})),
        'consultas_sql': ', '.join(sorted({str(l['consultas_sql']) for l in linhas})),
        'tempo_no_servidor_ms': mediana([l['tempo_no_servidor_ms'] for l in linhas]),
        'titulo': linhas[0]['titulo'], 'observacao': f'{observacao} (mediana de {len(linhas)})',
    }


# Leituras repetidas que a tabela em Markdown junta numa linha: prefixo -> a partir de qual leitura
GRUPOS = {'A4': 2, 'A5': 1, 'B5': 1}


def linhas_da_tabela(linhas):
    resumo = []
    for linha in linhas:
        prefixo, _, numero = linha['passo'].partition('.')
        if prefixo not in GRUPOS or int(numero) < GRUPOS[prefixo]:
            resumo.append(linha)
        elif int(numero) == GRUPOS[prefixo]:
            grupo = [l for l in linhas if l['passo'].startswith(f'{prefixo}.')
                     and int(l['passo'].partition('.')[2]) >= GRUPOS[prefixo]]
            resumo.append(agrupar(grupo, f"{grupo[0]['passo']} a {grupo[-1]['passo']}", grupo[0]['observacao']))
    return [[
        l['passo'], l['t_s'] if isinstance(l['t_s'], str) else br(l['t_s'], 1), l['operacao'], l['status'],
        l['cache'], '–' if l['consultas_sql'] is None else l['consultas_sql'],
        '–' if l['tempo_no_servidor_ms'] is None else br(l['tempo_no_servidor_ms'], 2), l['titulo'],
        l['observacao'],
    ] for l in resumo]


def esvaziar_o_cache(cliente):
    for _ in range(10):
        if cliente.requisitar('DELETE', '/api/laboratorio/cache').status == 200:
            return
        time.sleep(1)


def main():
    cliente = Cliente()
    esperar_api(cliente)
    estado = cliente.json('GET', '/api/laboratorio/estado')
    servidor = estado['banco']['servidor']
    original = sql_no_banco(f"SELECT titulo || '|' || atualizado_em FROM livro WHERE id = {LIVRO};")
    titulo_original, atualizado_original = original.rsplit('|', 1)
    for outro in range(101, 121):  # aquecimento: abre as conexões da API com o banco
        cliente.get(f'/api/livros/{outro}/sem-cache')

    try:
        linhas_a, titulo_da_parte_a = parte_a(cliente, titulo_original)
        linhas_b, conclusao = parte_b(cliente, titulo_original, titulo_da_parte_a)
    finally:
        print('Voltando ao estado inicial (Redis no ar, título original, cache vazio)...')
        compose('unpause', 'cache', verificar=False)
        compose('start', 'cache', verificar=False)
        esperar_redis_saudavel()
        sql_no_banco(f'UPDATE livro SET titulo = {literal(titulo_original)}, '
                     f'atualizado_em = {literal(atualizado_original)} WHERE id = {LIVRO};')
        esvaziar_o_cache(cliente)

    banco = 'PostgreSQL local (perfil banco-local)' if servidor == 'banco' else f'Supabase ({servidor})'
    configuracao = estado['configuracao']
    colunas = ['passo', 't (s)', 'operação', 'status', 'X-Cache', 'consultas SQL', 'tempo no servidor (ms)',
               'título devolvido', 'o que aconteceu']
    markdown = '\n\n'.join([
        f"Banco: {banco}. Tempo limite do Redis na API: {br(configuracao['cache_tempo_limite_s'], 1)} s; "
        f"vigia a cada {br(configuracao['cache_intervalo_da_vigia_s'], 1)} s. O tempo (t) conta a partir "
        'da queda do Redis.',
        '### A. Redis parado (`docker compose stop cache`)',
        tabela(colunas, linhas_da_tabela(linhas_a), 'edeeeddee'),
        f'### B. Redis travado por {TRAVADO_S} s (`docker compose pause cache`), com os dados na memória',
        tabela(colunas, linhas_da_tabela(linhas_b), 'edeeeddee'),
    ])
    gravar('falha_do_cache.md', markdown)
    gravar('falha_do_cache.json', {
        'ambiente': {'banco': servidor, 'configuracao': configuracao, 'versoes': estado['versoes']},
        'parte_a': linhas_a, 'parte_b': linhas_b,
    })
    print(markdown)
    print(f'\nParte B: {conclusao}')


if __name__ == '__main__':
    main()

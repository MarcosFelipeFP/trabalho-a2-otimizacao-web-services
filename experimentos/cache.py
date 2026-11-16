"""Item 1 (seções 3.4 e 3.5): o experimento obrigatório do cache, passo a passo.

  1. consulta a ficha de um livro e registra o comportamento do cache;
  2. repete a consulta e verifica se houve reaproveitamento;
  3. altera o livro por uma operação da aplicação (PUT), que invalida a ficha no cache;
  4. consulta de novo e confere que a informação voltou atualizada;
  5. demonstra a expiração: uma alteração feita direto no banco, por fora da API, não invalida
     o cache; a ficha antiga continua sendo servida até o TTL acabar.

Depois compara o tempo de resposta sem cache, com cache e acerto, e com cache e falha (3.5).

Para a espera do TTL não levar 10 minutos, o roteiro recria a API com TTL de 20 s e, no fim,
volta ao TTL padrão (600 s). As alterações no livro também são desfeitas no fim.

    python experimentos/cache.py            (com a API no ar: docker compose up -d)
"""

import random
import time
from datetime import datetime

from comum import (
    Cliente, br, esperar_api, gravar, literal, mediana, percentil, recriar_api, sql_no_banco, tabela,
)

LIVRO = 42
TTL_DA_DEMONSTRACAO = 20
TTL_PADRAO = 600


def hora(texto):
    """'2026-11-15T22:44:58.669062' -> '22:44:58.669'"""
    return datetime.fromisoformat(texto).strftime('%H:%M:%S.%f')[:-3]


def experimento_passo_a_passo(cliente):
    passos = []

    def registrar(passo, operacao, resposta, observacao=''):
        ficha = resposta.json()
        situacao = cliente.json('GET', f'/api/laboratorio/cache/livros/{LIVRO}')
        passos.append({
            'passo': passo,
            'operacao': operacao,
            'status': resposta.status,
            'x_cache': resposta.cabecalho('x-cache', '–'),
            'consultas_sql': resposta.consultas_sql,
            'tempo_no_servidor_ms': resposta.tempo_no_servidor_ms,
            'titulo': ficha['titulo'],
            'gerada_em': hora(ficha['gerada_em']),
            'ttl_restante_s': situacao['ttl_restante_segundos'],
            'observacao': observacao,
        })
        print(f"  {passo:>3}  {operacao:<48} {passos[-1]['x_cache']:<5} SQL={resposta.consultas_sql} "
              f"{resposta.tempo_no_servidor_ms:7.2f} ms  {ficha['titulo'][:45]}")

    url = f'/api/livros/{LIVRO}/com-cache'
    # Aquecimento: a API acabou de ser recriada e as primeiras requisições abrem as conexões com o
    # banco. O PUT repete o título atual (as alterações no livro são desfeitas no fim).
    for outro in range(101, 121):
        cliente.get(f'/api/livros/{outro}/sem-cache')
    titulo_atual = cliente.json('GET', f'/api/livros/{LIVRO}/sem-cache')['titulo']
    cliente.requisitar('PUT', f'/api/livros/{LIVRO}', {'titulo': titulo_atual})
    cliente.json('DELETE', '/api/laboratorio/cache')

    print(f'Experimento passo a passo com o livro {LIVRO} (TTL de {TTL_DA_DEMONSTRACAO} s):')

    registrar('1', 'GET com cache (cache vazio)', cliente.get(url), 'falha: monta a ficha no banco e guarda')
    registrar('2', 'GET com cache de novo', cliente.get(url), 'acerto: nenhuma consulta ao banco')
    titulo_original = passos[0]['titulo']

    novo_titulo = f'{titulo_original} (edição revista)'
    alteracao = cliente.requisitar('PUT', f'/api/livros/{LIVRO}', {'titulo': novo_titulo})
    passos.append({
        'passo': '3', 'operacao': 'PUT /api/livros/{id} (novo título)', 'status': alteracao.status,
        'x_cache': '–', 'consultas_sql': alteracao.consultas_sql,
        'tempo_no_servidor_ms': alteracao.tempo_no_servidor_ms, 'titulo': novo_titulo,
        'gerada_em': '–', 'ttl_restante_s': None,
        'observacao': f"ficha removida do cache (X-Cache-Invalidado: {alteracao.cabecalho('x-cache-invalidado')})",
    })
    print(f"    3  PUT: X-Cache-Invalidado = {alteracao.cabecalho('x-cache-invalidado')}")

    registrar('4a', 'GET com cache depois do PUT', cliente.get(url), 'falha: busca a versão nova no banco')
    registrar('4b', 'GET com cache de novo', cliente.get(url), 'acerto, já com o título novo')

    titulo_externo = f'{novo_titulo} [alterado direto no banco]'
    sql_no_banco(f'UPDATE livro SET titulo = {literal(titulo_externo)} WHERE id = {LIVRO};')
    passos.append({
        'passo': '5a', 'operacao': 'UPDATE direto no banco (por fora da API)', 'status': '–',
        'x_cache': '–', 'consultas_sql': None, 'tempo_no_servidor_ms': None, 'titulo': titulo_externo,
        'gerada_em': '–', 'ttl_restante_s': None, 'observacao': 'nada avisa o cache',
    })
    print('   5a  UPDATE direto no banco')
    registrar('5b', 'GET com cache', cliente.get(url), 'acerto com o título ANTIGO: dado desatualizado')

    espera = (passos[-1]['ttl_restante_s'] or 0) + 1.5
    print(f'       esperando {espera:.0f} s até o TTL acabar...')
    time.sleep(espera)
    # Parada, a conexão foi fechada pelo servidor (keep-alive de 5 s); a nova pode cair num
    # processo da API ainda sem conexões abertas com o banco. Aquece antes de medir.
    for outro in range(121, 131):
        cliente.get(f'/api/livros/{outro}/sem-cache')
    registrar('5c', 'GET com cache depois do TTL', cliente.get(url), 'a ficha expirou: falha e título atual')
    return passos, titulo_original


def comparar_tempos(cliente, quantidade=300):
    """Uma requisição por vez (sem concorrência), em livros sorteados com semente fixa."""
    livros = random.Random(2026).sample(range(1, 20001), quantidade)
    resultados = {}

    def medir(nome, url):
        respostas = [cliente.get(url.format(livro)) for livro in livros]
        servidor = [r.tempo_no_servidor_ms for r in respostas]
        resultados[nome] = {
            'requisicoes': len(respostas),
            'consultas_sql_por_requisicao': sum(r.consultas_sql for r in respostas) / len(respostas),
            'acertos': sum(r.cabecalho('x-cache') == 'HIT' for r in respostas),
            'servidor_mediana_ms': mediana(servidor),
            'servidor_p95_ms': percentil(servidor, 0.95),
            'cliente_mediana_ms': mediana([r.tempo_ms for r in respostas]),
        }

    for livro in livros[:50]:  # aquecimento
        cliente.get(f'/api/livros/{livro}/sem-cache')
    medir('sem cache', '/api/livros/{}/sem-cache')
    cliente.json('DELETE', '/api/laboratorio/cache')
    medir('com cache, falha (cache vazio)', '/api/livros/{}/com-cache')
    medir('com cache, acerto (mesmos livros de novo)', '/api/livros/{}/com-cache')
    return resultados


def main():
    cliente = Cliente()
    esperar_api(cliente)
    original = sql_no_banco(f"SELECT titulo || '|' || atualizado_em FROM livro WHERE id = {LIVRO};")
    titulo_original, atualizado_original = original.rsplit('|', 1)

    recriar_api(cliente, TTL_DA_DEMONSTRACAO)
    try:
        passos, _ = experimento_passo_a_passo(cliente)
    finally:
        sql_no_banco(f'UPDATE livro SET titulo = {literal(titulo_original)}, '
                     f'atualizado_em = {literal(atualizado_original)} WHERE id = {LIVRO};')
        print(f'Voltando a API ao TTL padrão ({TTL_PADRAO} s) e desfazendo as alterações no livro...')
        recriar_api(cliente, TTL_PADRAO)
        cliente.json('DELETE', '/api/laboratorio/cache')

    print('Comparando tempos (uma requisição por vez, 300 livros)...')
    tempos = comparar_tempos(cliente)
    cliente.json('DELETE', '/api/laboratorio/cache')

    linhas_passos = [[
        p['passo'], p['operacao'], p['x_cache'],
        '–' if p['consultas_sql'] is None else p['consultas_sql'],
        '–' if p['tempo_no_servidor_ms'] is None else br(p['tempo_no_servidor_ms'], 2),
        p['titulo'], p['gerada_em'],
        '–' if p['ttl_restante_s'] is None else f"{p['ttl_restante_s']} s",
        p['observacao'],
    ] for p in passos]
    linhas_tempos = [[
        nome, br(t['consultas_sql_por_requisicao'], 1), f"{t['acertos']} de {t['requisicoes']}",
        br(t['servidor_mediana_ms'], 2), br(t['servidor_p95_ms'], 2), br(t['cliente_mediana_ms'], 2),
    ] for nome, t in tempos.items()]

    markdown = '\n\n'.join([
        f'### Experimento passo a passo (livro {LIVRO}, TTL de {TTL_DA_DEMONSTRACAO} s)',
        tabela(['passo', 'operação', 'X-Cache', 'consultas SQL', 'tempo no servidor (ms)', 'título devolvido',
                'ficha gerada às', 'TTL restante', 'o que aconteceu'], linhas_passos, 'eeeddeede'),
        '### Tempo de resposta sem e com cache (uma requisição por vez, 300 livros sorteados)',
        tabela(['situação', 'consultas SQL por requisição', 'acertos', 'servidor: mediana (ms)',
                'servidor: p95 (ms)', 'total no cliente: mediana (ms)'], linhas_tempos),
    ])
    gravar('cache.md', markdown)
    gravar('cache.json', {'passos': passos, 'tempos': tempos})
    print(markdown)


if __name__ == '__main__':
    main()

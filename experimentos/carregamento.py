"""Item 2 (seções 4.1 a 4.4): LAZY, EAGER e as versões otimizadas, com quantidades diferentes.

Para cada estratégia e cada quantidade de empréstimos por página (10, 50, 100, 500 e 1.000):
  - comandos SQL executados, linhas e bytes devolvidos pelo banco e tamanho da resposta, pela
    rota de laboratório que registra cada comando;
  - tempo no servidor e tempo no banco (cabeçalho Server-Timing), mediana de várias requisições,
    uma por vez.
Também compara as versões "resumo" (a resposta não usa livro nem leitor) e grava o SQL que cada
estratégia gera para 3 empréstimos, na ordem em que foi executado (resultados/sql/).

    python experimentos/carregamento.py      (com a API no ar: docker compose up -d)
"""

from comum import Cliente, br, esperar_api, gravar, mediana, tabela

ESTRATEGIAS = ['lazy', 'eager', 'eager-selectin', 'eager-immediate', 'join-fetch', 'otimizada', 'nativa']
DESCRICOES = {
    'lazy': 'LAZY (lazy="select")',
    'eager': 'EAGER (lazy="joined")',
    'eager-selectin': 'EAGER com SELECT ... IN',
    'eager-immediate': 'EAGER imediato, um SELECT por objeto',
    'join-fetch': 'JOIN FETCH (joinedload)',
    'otimizada': 'otimizada (projeção com JOIN)',
    'nativa': 'SQL nativo',
}
QUANTIDADES = [10, 50, 100, 500, 1000]
DESDE = 150_000  # primeira página medida: empréstimos 150.000 em diante


def repeticoes(quantidade):
    return 21 if quantidade <= 100 else 9 if quantidade <= 500 else 5


def medir(cliente, caminho, vezes):
    cliente.get(caminho)  # aquecimento
    respostas = [cliente.get(caminho) for _ in range(vezes)]
    assert all(r.status == 200 for r in respostas), caminho
    return {
        'consultas_sql': respostas[0].consultas_sql,
        'servidor_ms': mediana([r.tempo_no_servidor_ms for r in respostas]),
        'banco_ms': mediana([r.tempo_no_banco_ms for r in respostas]),
        'corpo': respostas[0].corpo,
    }


def volume(cliente, caminho_do_laboratorio):
    dados = cliente.json('GET', caminho_do_laboratorio)
    return {
        'consultas': dados['consultas'],
        'linhas_lidas': dados['linhas_lidas_do_banco'],
        'bytes_lidos': dados['bytes_lidos_do_banco'],
        'bytes_da_resposta': dados['bytes_da_resposta'],
        'comandos': dados['comandos'],
    }


def gravar_sql(cliente):
    """O SQL que cada estratégia executa para 3 empréstimos, na ordem de execução."""
    for estrategia in ESTRATEGIAS:
        dados = cliente.json('GET', f'/api/laboratorio/sql/emprestimos/{estrategia}?desde_id={DESDE}&quantidade=3')
        partes = [f'-- {DESCRICOES[estrategia]}: GET /api/emprestimos/{estrategia}?desde_id={DESDE}&quantidade=3',
                  f'-- {dados["consultas"]} comandos, {dados["linhas_lidas_do_banco"]} linhas e '
                  f'{dados["bytes_lidos_do_banco"]} bytes devolvidos pelo banco', '']
        for numero, comando in enumerate(dados['comandos'], 1):
            partes.append(f'-- {numero}) {comando["linhas"]} linha(s), {comando["colunas"]} colunas, '
                          f'{comando["bytes"]} bytes; parâmetros: {comando["parametros"]}')
            partes.append(comando['sql'].strip() + ';')
            partes.append('')
        gravar(f'sql/{estrategia}.sql', '\n'.join(partes))


def main():
    cliente = Cliente()
    esperar_api(cliente)
    resultados = {}
    referencia = {}
    for quantidade in QUANTIDADES:
        print(f'{quantidade} empréstimos por página:')
        for estrategia in ESTRATEGIAS:
            caminho = f'/api/emprestimos/{estrategia}?desde_id={DESDE}&quantidade={quantidade}'
            tempos = medir(cliente, caminho, repeticoes(quantidade))
            dados = volume(cliente, f'/api/laboratorio/sql/emprestimos/{estrategia}?desde_id={DESDE}&quantidade={quantidade}')
            # todas as estratégias precisam devolver exatamente o mesmo JSON
            referencia.setdefault(quantidade, tempos['corpo'])
            if tempos['corpo'] != referencia[quantidade]:
                raise SystemExit(f'{estrategia} devolveu um JSON diferente do LAZY com {quantidade} itens')
            resultados[(quantidade, estrategia)] = {**dados, **{k: v for k, v in tempos.items() if k != 'corpo'}}
            print(f'  {estrategia:<16} {dados["consultas"]:>5} consultas  {dados["linhas_lidas"]:>6} linhas  '
                  f'{dados["bytes_lidos"] / 1024:8.1f} KB  servidor {tempos["servidor_ms"]:8.2f} ms  '
                  f'banco {tempos["banco_ms"]:8.2f} ms')

    resumos = {}
    for quantidade in (20, 1000):
        for estrategia in ('lazy', 'eager'):
            caminho = f'/api/emprestimos/{estrategia}/resumo?desde_id={DESDE}&quantidade={quantidade}'
            tempos = medir(cliente, caminho, repeticoes(quantidade))
            dados = volume(cliente, f'/api/laboratorio/sql/emprestimos/{estrategia}/resumo?desde_id={DESDE}&quantidade={quantidade}')
            resumos[(quantidade, estrategia)] = {**dados, **{k: v for k, v in tempos.items() if k != 'corpo'}}
    gravar_sql(cliente)

    secoes = []
    for quantidade in QUANTIDADES:
        linhas = []
        for estrategia in ESTRATEGIAS:
            r = resultados[(quantidade, estrategia)]
            linhas.append([DESCRICOES[estrategia], br(r['consultas']), br(r['linhas_lidas']),
                           br(r['bytes_lidos'] / 1024, 1), br(r['bytes_da_resposta'] / 1024, 1),
                           br(r['banco_ms'], 2), br(r['servidor_ms'], 2)])
        secoes.append(f'#### {br(quantidade)} empréstimos por página')
        secoes.append(tabela(['estratégia', 'consultas SQL', 'linhas lidas do banco', 'KB lidos do banco',
                              'KB da resposta', 'tempo no banco (ms)', 'tempo no servidor (ms)'], linhas))

    # quantas consultas cada estratégia faz, conforme a quantidade cresce
    crescimento = [[DESCRICOES[e]] + [br(resultados[(q, e)]['consultas']) for q in QUANTIDADES] for e in ESTRATEGIAS]
    tempos = [[DESCRICOES[e]] + [br(resultados[(q, e)]['servidor_ms'], 1) for q in QUANTIDADES] for e in ESTRATEGIAS]
    linhas_resumo = []
    for (quantidade, estrategia), r in resumos.items():
        linhas_resumo.append([br(quantidade), estrategia.upper(), br(r['consultas']), br(r['bytes_lidos'] / 1024, 1),
                              br(r['bytes_da_resposta'] / 1024, 1), br(r['banco_ms'], 2), br(r['servidor_ms'], 2)])

    cabecalho_q = ['estratégia'] + [br(q) for q in QUANTIDADES]
    markdown = '\n\n'.join([
        '### Consultas SQL por requisição, conforme a quantidade de empréstimos da página',
        tabela(cabecalho_q, crescimento),
        '### Tempo no servidor (ms, mediana), conforme a quantidade de empréstimos da página',
        tabela(cabecalho_q, tempos),
        '### Detalhe por quantidade',
        *secoes,
        '### Resposta que não usa livro nem leitor (versões "resumo")',
        tabela(['empréstimos', 'mapeamento', 'consultas SQL', 'KB lidos do banco', 'KB da resposta',
                'tempo no banco (ms)', 'tempo no servidor (ms)'], linhas_resumo, 'deddddd'),
    ])
    gravar('carregamento.md', markdown)
    gravar('carregamento.json', {
        f'{q}_{e}': {k: v for k, v in r.items() if k != 'comandos'} for (q, e), r in resultados.items()
    })
    print(markdown)


if __name__ == '__main__':
    main()

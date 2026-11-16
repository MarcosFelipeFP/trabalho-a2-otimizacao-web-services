"""Item 2 (seção 5): índice para o histórico de empréstimos de um leitor.

    SELECT ... FROM emprestimo JOIN livro ON livro.id = emprestimo.livro_id
    WHERE emprestimo.leitor_id = ? ORDER BY emprestimo.data_emprestimo DESC

Situações comparadas, para um leitor típico (150) e para o leitor com mais empréstimos:
  1. sem índice em emprestimo(leitor_id): o estado inicial do banco;
  2. índice só em leitor_id;
  3. índice (leitor_id, data_emprestimo DESC), o proposto;
  4. o índice proposto, com random_page_cost = 1,1 (custo para dados em memória ou SSD);
  5. o índice proposto, pedindo só os 10 mais recentes (LIMIT 10).
Para cada uma: o plano de execução (EXPLAIN ANALYZE, gravado em resultados/planos/), o tempo de
execução no banco (mediana de 15 EXPLAIN ANALYZE) e o tempo da requisição na API (mediana de 30).

Depois: a busca por intervalo (empréstimos atrasados) sem e com índice parcial, o tamanho de cada
índice e, por último, o custo de escrita (inserir 20.000 empréstimos, desfeito com ROLLBACK) com 0,
1 e 3 índices extras. Os testes de escrita deixam linhas mortas, por isso vêm no fim e são
seguidos de VACUUM e REINDEX: o banco volta ao estado inicial, sem os índices do experimento.

    python experimentos/indices.py       (com a API no ar: docker compose up -d)
"""

from comum import Cliente, br, esperar_api, gravar, mediana, sql_no_banco, tabela

INDICES_DO_EXPERIMENTO = ['leitor-data', 'leitor', 'em-aberto']


def tamanho(bytes_):
    return f'{br(bytes_ / 2 ** 20, 1)} MB' if bytes_ >= 2 ** 20 else f'{br(bytes_ / 1024)} KB'


def estado_dos_indices(cliente, criar):
    for nome in INDICES_DO_EXPERIMENTO:
        cliente.json('PUT' if nome in criar else 'DELETE', f'/api/laboratorio/indices/{nome}')


def explicar(cliente, caminho, vezes=15):
    planos = [cliente.json('GET', caminho) for _ in range(vezes)]
    plano = planos[-1]
    return {**plano, 'tempo_de_execucao_mediano_ms': mediana([p['tempo_de_execucao_ms'] for p in planos])}


def tempo_na_api(cliente, caminho, vezes=30):
    cliente.get(caminho)
    respostas = [cliente.get(caminho) for _ in range(vezes)]
    return mediana([r.tempo_no_banco_ms for r in respostas]), mediana([r.tempo_no_servidor_ms for r in respostas])


def resumo_das_operacoes(plano):
    partes = []
    for operacao in plano['operacoes']:
        if operacao['operacao'] in ('Seq Scan', 'Parallel Seq Scan', 'Index Scan', 'Index Only Scan',
                                    'Bitmap Index Scan', 'Bitmap Heap Scan', 'Sort', 'Incremental Sort',
                                    'Limit'):
            alvo = operacao['indice'] or operacao['tabela'] or ''
            if operacao['operacao'] == 'Index Scan' and operacao['tabela'] == 'livro':
                continue  # o JOIN com livro usa a chave primária em todas as situações
            partes.append(f"{operacao['operacao']}{' ' + alvo if alvo else ''}")
    return ' → '.join(partes)


def main():
    cliente = Cliente()
    esperar_api(cliente)
    cliente.json('POST', '/api/laboratorio/banco/aquecer')
    mais_ativo, emprestimos_do_mais_ativo = sql_no_banco(
        'SELECT leitor_id, count(*) FROM emprestimo GROUP BY leitor_id ORDER BY 2 DESC, 1 LIMIT 1;').split('|')
    leitores = {150: sql_no_banco('SELECT count(*) FROM emprestimo WHERE leitor_id = 150;'),
                int(mais_ativo): emprestimos_do_mais_ativo}

    situacoes = [
        ('sem índice', [], ''),
        ('índice só em leitor_id', ['leitor'], ''),
        ('índice (leitor_id, data_emprestimo DESC)', ['leitor-data'], ''),
        ('índice proposto + random_page_cost 1,1', ['leitor-data'], '&random_page_cost=1.1'),
        ('índice proposto + LIMIT 10', ['leitor-data'], '&limite=10'),
    ]
    linhas, detalhes = [], {}
    try:
        for numero, (nome, criar, extra) in enumerate(situacoes, 1):
            estado_dos_indices(cliente, criar)
            for leitor, quantidade in leitores.items():
                plano = explicar(cliente, f'/api/laboratorio/explain/historico?leitor_id={leitor}{extra}')
                consulta_api = f'/api/leitores/{leitor}/emprestimos' + ('?limite=10' if 'limite' in extra else '')
                banco_ms, servidor_ms = (None, None) if 'random_page_cost' in extra else tempo_na_api(cliente, consulta_api)
                descartadas = sum(o['linhas_descartadas_pelo_filtro'] for o in plano['operacoes'])
                linhas.append([f'{numero}. {nome}', f'{leitor} ({quantidade})', resumo_das_operacoes(plano),
                               'sim' if plano['tem_ordenacao'] else 'não', br(descartadas),
                               br(plano['tempo_de_execucao_mediano_ms'], 3),
                               '–' if banco_ms is None else br(banco_ms, 2),
                               '–' if servidor_ms is None else br(servidor_ms, 2)])
                detalhes[f'{numero}_{leitor}'] = plano
                gravar(f'planos/{numero}_leitor{leitor}.txt',
                       f'-- {nome}; leitor {leitor} ({quantidade} empréstimos)\n'
                       f'-- índices em emprestimo: {", ".join(plano["indices_existentes"])}\n'
                       f'-- random_page_cost: {plano["random_page_cost"]}\n\n'
                       + plano['sql'] + '\n\n' + '\n'.join(plano['plano']))
                print(f'{numero}. {nome:<44} leitor {leitor:>5}: {plano["tempo_de_execucao_mediano_ms"]:8.3f} ms  '
                      f'{resumo_das_operacoes(plano)}')

        # busca por intervalo: empréstimos atrasados
        intervalo = []
        for nome, criar in [('sem índice parcial', []), ('com índice parcial (em aberto)', ['em-aberto'])]:
            estado_dos_indices(cliente, criar)
            plano = explicar(cliente, '/api/laboratorio/explain/atrasados?limite=50')
            banco_ms, servidor_ms = tempo_na_api(cliente, '/api/emprestimos/atrasados?limite=50')
            intervalo.append([nome, resumo_das_operacoes(plano),
                              br(sum(o['linhas_descartadas_pelo_filtro'] for o in plano['operacoes'])),
                              br(plano['tempo_de_execucao_mediano_ms'], 3), br(banco_ms, 2), br(servidor_ms, 2)])
            gravar(f'planos/atrasados_{"com" if criar else "sem"}_indice.txt',
                   plano['sql'] + '\n\n' + '\n'.join(plano['plano']))

        # tamanho de cada índice, recém-criado (antes dos testes de escrita, que incham os índices)
        estado_dos_indices(cliente, INDICES_DO_EXPERIMENTO)
        tamanhos = [[i['nome'], i['definicao'].split(' USING btree ')[-1], tamanho(i['bytes'])]
                    for i in cliente.json('GET', '/api/laboratorio/indices')]

        # custo de escrita: cada medida insere 20.000 linhas e desfaz (ROLLBACK)
        escrita = []
        for nome, criar in [('nenhum índice do experimento', []),
                            ('(leitor_id, data_emprestimo DESC)', ['leitor-data']),
                            ('os três índices do experimento', INDICES_DO_EXPERIMENTO)]:
            estado_dos_indices(cliente, criar)
            indices = cliente.json('GET', '/api/laboratorio/indices')  # tamanhos antes das escritas
            cliente.json('POST', '/api/laboratorio/indices/custo-de-escrita?linhas=2000')  # aquecimento
            medidas = [cliente.json('POST', '/api/laboratorio/indices/custo-de-escrita?linhas=20000') for _ in range(5)]
            escrita.append([nome, ', '.join(medidas[0]['indices']),
                            tamanho(sum(i['bytes'] for i in indices if i['nome'] in medidas[0]['indices'])),
                            br(mediana([m['duracao_ms'] for m in medidas]), 0),
                            br(mediana([m['microssegundos_por_linha'] for m in medidas]), 1)])
            print(f'escrita com {nome}: {mediana([m["duracao_ms"] for m in medidas]):.0f} ms')
            cliente.json('POST', '/api/laboratorio/banco/manutencao')  # limpa o que o ROLLBACK deixou
    finally:
        estado_dos_indices(cliente, [])
        cliente.json('POST', '/api/laboratorio/banco/manutencao')

    markdown = '\n\n'.join([
        '### Histórico de empréstimos de um leitor (planos em resultados/planos/)',
        tabela(['situação', 'leitor (empréstimos)', 'operações em emprestimo', 'ordenação (Sort)',
                'linhas descartadas pelo filtro', 'execução no banco (ms)', 'tempo no banco pela API (ms)',
                'tempo no servidor (ms)'], linhas, 'eeeedddd'),
        '### Tamanho dos índices da tabela emprestimo (com os três índices do experimento criados)',
        tabela(['índice', 'colunas', 'tamanho'], tamanhos, 'eed'),
        '### Custo de escrita: inserir 20.000 empréstimos (desfeito com ROLLBACK), mediana de 5',
        tabela(['índices extras', 'índices existentes', 'tamanho dos índices', 'tempo (ms)', 'µs por linha'], escrita, 'eeddd'),
        '### Busca por intervalo: 50 empréstimos atrasados mais antigos',
        tabela(['situação', 'operações em emprestimo', 'linhas descartadas pelo filtro', 'execução no banco (ms)',
                'tempo no banco pela API (ms)', 'tempo no servidor (ms)'], intervalo, 'eedddd'),
    ])
    gravar('indices.md', markdown)
    gravar('indices.json', detalhes)
    print(markdown)


if __name__ == '__main__':
    main()

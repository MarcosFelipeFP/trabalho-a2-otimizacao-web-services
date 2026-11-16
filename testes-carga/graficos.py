"""Gráficos de linhas em SVG, sem dependências externas.

Uma figura tem um título, a legenda e um painel por métrica (latência média, p95,
p99, vazão...). Em todos os painéis cada versão mantém a mesma cor, e o eixo x são
os níveis de carga. O SVG traz o tema claro e o escuro (segue a preferência do
sistema) e cada ponto tem uma dica com o valor exato ao passar o mouse.
"""
from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

# Paleta categórica (ordem fixa) conferida para daltonismo, nas versões clara e escura.
CORES = [('#2a78d6', '#3987e5'), ('#eb6834', '#d95926'), ('#1baf7a', '#199e70'), ('#eda100', '#c98500')]

ESTILO = """
svg { --fundo: #fcfcfb; --tinta1: #0b0b0b; --tinta2: #52514e; --tinta3: #898781;
      --grade: #e1e0d9; --eixo: #c3c2b7; %(claras)s
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
@media (prefers-color-scheme: dark) {
  svg { --fundo: #1a1a19; --tinta1: #f0efec; --tinta2: #c3c2b7; --tinta3: #898781;
        --grade: #2c2c2a; --eixo: #383835; %(escuras)s }
}
.fundo { fill: var(--fundo); }
.grade { stroke: var(--grade); stroke-width: 1; }
.eixo { stroke: var(--eixo); stroke-width: 1; }
.t1 { fill: var(--tinta1); }
.t2 { fill: var(--tinta2); }
.t3 { fill: var(--tinta3); }
.num { font-variant-numeric: tabular-nums; }
.linha { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.ponto { stroke: var(--fundo); stroke-width: 2; }
%(series)s
"""

LARGURA = 960
MARGEM = 24
ALTURA_PAINEL = 250
VAO = 28


def br(valor, casas=0):
    texto = f'{valor:,.{casas}f}'
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def _estilo(quantidade):
    claras = ' '.join(f'--s{i}: {CORES[i - 1][0]};' for i in range(1, quantidade + 1))
    escuras = ' '.join(f'--s{i}: {CORES[i - 1][1]};' for i in range(1, quantidade + 1))
    series = '\n'.join(f'.c{i} .linha {{ stroke: var(--s{i}); }} .c{i} .ponto {{ fill: var(--s{i}); }}'
                       for i in range(1, quantidade + 1))
    return ESTILO % {'claras': claras, 'escuras': escuras, 'series': series}


def _passo(maximo, divisoes=4):
    """Passo "redondo" (1, 2, 2,5 ou 5 vezes uma potência de 10) para cerca de 4 divisões."""
    if maximo <= 0:
        return 1
    bruto = maximo / divisoes
    potencia = 10 ** math.floor(math.log10(bruto))
    for multiplo in (1, 2, 2.5, 5, 10):
        if multiplo * potencia >= bruto:
            return multiplo * potencia
    return 10 * potencia


def _rotulo(valor, passo, compacto):
    """Rótulo do eixo com só as casas decimais necessárias (2,5 e não 2; 10 e não 10,0)."""
    if compacto:
        valor = valor / 1000
    texto = br(valor, 2)
    if ',' in texto:
        texto = texto.rstrip('0').rstrip(',')
    return f'{texto} mil' if compacto and valor != 0 else texto


def _largura_texto(texto, tamanho):
    return len(texto) * tamanho * 0.58


def _painel(x0, y0, largura, altura, titulo, unidade, rotulos_x, titulo_x, series, valores):
    partes = [f'<text class="t1" x="{x0}" y="{y0 + 14}" font-size="13" font-weight="600">{escape(titulo)}</text>']
    esquerda, direita = x0 + 56, x0 + largura - 92
    topo, base = y0 + 32, y0 + altura - 40

    todos = [v for serie in series for v in valores[serie] if v is not None]
    passo = _passo(max(todos) if todos else 1)
    teto = passo * max(1, math.ceil((max(todos) if todos else 1) / passo))
    compacto = teto >= 10000

    def y(valor):
        return base - (valor / teto) * (base - topo)

    marca = 0.0
    while marca <= teto + passo / 1000:
        yy = y(marca)
        classe = 'eixo' if marca == 0 else 'grade'
        partes.append(f'<line class="{classe}" x1="{esquerda}" y1="{yy:.1f}" x2="{direita}" y2="{yy:.1f}"/>')
        partes.append(f'<text class="t3 num" x="{esquerda - 8}" y="{yy + 4:.1f}" font-size="11" '
                      f'text-anchor="end">{escape(_rotulo(marca, passo, compacto))}</text>')
        marca += passo

    n = len(rotulos_x)
    interno = 14
    if n == 1:
        xs = [(esquerda + direita) / 2]
    else:
        xs = [esquerda + interno + i * (direita - esquerda - 2 * interno) / (n - 1) for i in range(n)]
    for x, rotulo in zip(xs, rotulos_x):
        partes.append(f'<text class="t3 num" x="{x:.1f}" y="{base + 17}" font-size="11" '
                      f'text-anchor="middle">{escape(str(rotulo))}</text>')
    partes.append(f'<text class="t3" x="{(esquerda + direita) / 2:.1f}" y="{base + 33}" font-size="11" '
                  f'text-anchor="middle">{escape(titulo_x)}</text>')

    # linhas primeiro, pontos por cima (com o anel na cor do fundo)
    for indice, serie in enumerate(series, 1):
        trechos, atual = [], []
        for x, valor in zip(xs, valores[serie]):
            if valor is None:
                if atual:
                    trechos.append(atual)
                atual = []
            else:
                atual.append((x, y(valor)))
        if atual:
            trechos.append(atual)
        caminho = ' '.join('M ' + ' L '.join(f'{px:.1f} {py:.1f}' for px, py in trecho) for trecho in trechos)
        if caminho:
            partes.append(f'<g class="c{indice}"><path class="linha" d="{caminho}"/></g>')
    for indice, serie in enumerate(series, 1):
        pontos = []
        for x, rotulo, valor in zip(xs, rotulos_x, valores[serie]):
            if valor is not None:
                dica = f'{serie} · {rotulo} {titulo_x.split()[0]} · {br(valor, 1 if valor < 100 else 0)} {unidade}'
                pontos.append(f'<circle class="ponto" cx="{x:.1f}" cy="{y(valor):.1f}" r="4">'
                              f'<title>{escape(dica)}</title></circle>')
        partes.append(f'<g class="c{indice}">' + ''.join(pontos) + '</g>')

    # Rótulos no fim das linhas. Linhas que terminam juntas ganham um rótulo só ("lazy e eager");
    # se o nome combinado não couber, fica o da linha desenhada por cima, e a legenda cobre o resto.
    finais = sorted((y(valores[serie][-1]), indice, serie)
                    for indice, serie in enumerate(series) if valores[serie][-1] is not None)
    grupos = []
    for yy, indice, serie in finais:
        if grupos and yy - grupos[-1][-1][0] < 13:
            grupos[-1].append((yy, indice, serie))
        else:
            grupos.append([(yy, indice, serie)])
    espaco = x0 + largura - (xs[-1] + 10)
    ultimo_y = None
    for grupo in grupos:
        nomes = [serie for _, _, serie in sorted(grupo, key=lambda item: item[1])]
        texto = nomes[0] if len(nomes) == 1 else ', '.join(nomes[:-1]) + ' e ' + nomes[-1]
        if _largura_texto(texto, 11) > espaco:
            texto = nomes[-1]
        yy = sum(item[0] for item in grupo) / len(grupo)
        if ultimo_y is None or yy - ultimo_y >= 13:
            partes.append(f'<text class="t2" x="{xs[-1] + 10:.1f}" y="{yy + 4:.1f}" font-size="11">'
                          f'{escape(texto)}</text>')
            ultimo_y = yy
    return '\n'.join(partes)


def figura(arquivo, titulo, subtitulo, rotulos_x, titulo_x, series, paineis):
    """Desenha um painel por métrica e grava o SVG.

    series: nomes das versões, na ordem das cores.
    paineis: lista de dicionários {"titulo", "unidade", "valores": {serie: [valor por rótulo de x]}}.
    """
    if len(series) > len(CORES):
        raise ValueError(f'no máximo {len(CORES)} séries por figura')
    colunas = 2 if len(paineis) > 1 else 1
    linhas = math.ceil(len(paineis) / colunas)
    largura_painel = (LARGURA - 2 * MARGEM - (colunas - 1) * VAO) / colunas
    topo_paineis = MARGEM + 76
    altura = topo_paineis + linhas * ALTURA_PAINEL + (linhas - 1) * VAO + MARGEM

    descricao = f'{subtitulo}. Séries: {", ".join(series)}. Eixo x: {titulo_x} ({", ".join(map(str, rotulos_x))}).'
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{altura:.0f}" '
        f'viewBox="0 0 {LARGURA} {altura:.0f}" role="img" aria-labelledby="titulo descricao">',
        f'<title id="titulo">{escape(titulo)}</title>',
        f'<desc id="descricao">{escape(descricao)}</desc>',
        f'<style>{_estilo(len(series))}</style>',
        f'<rect class="fundo" width="{LARGURA}" height="{altura:.0f}" rx="8"/>',
        f'<text class="t1" x="{MARGEM}" y="{MARGEM + 16}" font-size="17" font-weight="600">{escape(titulo)}</text>',
        f'<text class="t2" x="{MARGEM}" y="{MARGEM + 38}" font-size="12">{escape(subtitulo)}</text>',
    ]

    x = MARGEM
    y_legenda = MARGEM + 60
    for indice, serie in enumerate(series, 1):
        partes.append(f'<g class="c{indice}"><line class="linha" x1="{x}" y1="{y_legenda}" x2="{x + 18}" '
                      f'y2="{y_legenda}"/><circle class="ponto" cx="{x + 9}" cy="{y_legenda}" r="4"/></g>')
        partes.append(f'<text class="t2" x="{x + 24}" y="{y_legenda + 4}" font-size="12">{escape(serie)}</text>')
        x += 24 + _largura_texto(serie, 12) + 22

    for numero, painel in enumerate(paineis):
        linha, coluna = divmod(numero, colunas)
        x0 = MARGEM + coluna * (largura_painel + VAO)
        y0 = topo_paineis + linha * (ALTURA_PAINEL + VAO)
        partes.append(_painel(x0, y0, largura_painel, ALTURA_PAINEL, painel['titulo'], painel['unidade'],
                              rotulos_x, titulo_x, series, painel['valores']))
    partes.append('</svg>')
    Path(arquivo).write_text('\n'.join(partes) + '\n', encoding='utf-8')

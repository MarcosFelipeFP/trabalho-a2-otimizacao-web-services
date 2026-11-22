"""Mapeamento objeto-relacional (SQLAlchemy) das tabelas da biblioteca.

O relacionamento comparado no item 2 do trabalho é Empréstimo -> Livro e Empréstimo -> Leitor.
A estratégia de carregamento fica declarada no mapeamento, como o FetchType do JPA:

    lazy="select"  ->  LAZY: o livro só é buscado quando o código acessa emprestimo.livro
    lazy="joined"  ->  EAGER: o livro vem junto, com JOIN, na mesma consulta do empréstimo

Por isso a tabela emprestimo é mapeada duas vezes: Emprestimo (LAZY, usado em toda a API) e
EmprestimoEager (EAGER, só leitura, usado na comparação).

As tabelas têm muitas colunas, como os cadastros de uma biblioteca real (banco/01-esquema.sql), e
todas estão mapeadas: carregar uma entidade, seja por LAZY ou por EAGER, traz todas elas, mesmo
quando a resposta usa só uma ou duas. As consultas otimizadas (projeções) buscam só as colunas
que usam.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]


class Autor(Base):
    __tablename__ = "autor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    nacionalidade: Mapped[str]
    biografia: Mapped[str | None]
    ano_nascimento: Mapped[int | None]
    ano_falecimento: Mapped[int | None]
    cidade_natal: Mapped[str | None]
    site: Mapped[str | None]
    premios: Mapped[str | None]


class Livro(Base):
    __tablename__ = "livro"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str]
    isbn: Mapped[str]
    editora: Mapped[str]
    ano_publicacao: Mapped[int]
    paginas: Mapped[int]
    sinopse: Mapped[str]
    autor_id: Mapped[int] = mapped_column(ForeignKey("autor.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    total_exemplares: Mapped[int]
    exemplares_disponiveis: Mapped[int]
    atualizado_em: Mapped[datetime]
    # ficha catalográfica
    subtitulo: Mapped[str | None]
    edicao: Mapped[int]
    ano_edicao: Mapped[int | None]
    local_publicacao: Mapped[str | None]
    idioma: Mapped[str]
    idioma_original: Mapped[str | None]
    tradutor: Mapped[str | None]
    ilustrador: Mapped[str | None]
    colecao: Mapped[str | None]
    volume: Mapped[int | None]
    formato: Mapped[str | None]
    largura_cm: Mapped[Decimal | None]
    altura_cm: Mapped[Decimal | None]
    espessura_cm: Mapped[Decimal | None]
    peso_g: Mapped[int | None]
    isbn10: Mapped[str | None]
    cdd: Mapped[str | None]
    cutter: Mapped[str | None]
    assuntos: Mapped[str | None]
    publico_alvo: Mapped[str | None]
    classificacao_indicativa: Mapped[str | None]
    sumario: Mapped[str | None]
    notas: Mapped[str | None]
    url_capa: Mapped[str | None]
    # acervo
    codigo_barras: Mapped[str | None]
    localizacao: Mapped[str | None]
    estado_conservacao: Mapped[str | None]
    origem: Mapped[str | None]
    data_aquisicao: Mapped[date | None]
    preco_aquisicao: Mapped[Decimal | None]
    fornecedor: Mapped[str | None]
    nota_fiscal: Mapped[str | None]
    avaliacao_media: Mapped[Decimal | None]
    total_avaliacoes: Mapped[int]
    cadastrado_em: Mapped[datetime]
    # descrição bibliográfica estendida e controle do acervo
    titulo_original: Mapped[str | None]
    serie: Mapped[str | None]
    numero_na_serie: Mapped[int | None]
    doi: Mapped[str | None]
    oclc: Mapped[str | None]
    lccn: Mapped[str | None]
    cdd_completa: Mapped[str | None]
    palavras_chave: Mapped[str | None]
    resumo_ingles: Mapped[str | None]
    tem_indice_remissivo: Mapped[bool]
    tem_bibliografia: Mapped[bool]
    ilustracoes: Mapped[str | None]
    encadernacao: Mapped[str | None]
    papel: Mapped[str | None]
    tiragem: Mapped[int | None]
    reimpressao: Mapped[int]
    data_lancamento: Mapped[date | None]
    preco_capa: Mapped[Decimal | None]
    moeda: Mapped[str]
    distribuidora: Mapped[str | None]
    direitos_autorais: Mapped[str | None]
    tombo: Mapped[str | None]
    setor: Mapped[str | None]
    corredor: Mapped[str | None]
    ultima_conferencia: Mapped[date | None]
    ultima_higienizacao: Mapped[date | None]
    reservas_ativas: Mapped[int]
    indicado_para: Mapped[str | None]
    premiacoes: Mapped[str | None]
    resenha: Mapped[str | None]
    registro_marc: Mapped[str | None]
    atualizado_por: Mapped[str | None]

    autor: Mapped[Autor] = relationship(lazy="select")
    categoria: Mapped[Categoria] = relationship(lazy="select")


class Leitor(Base):
    __tablename__ = "leitor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]
    email: Mapped[str]
    cadastrado_em: Mapped[date]
    numero_carteirinha: Mapped[str | None]
    data_nascimento: Mapped[date | None]
    tipo: Mapped[str | None]
    matricula: Mapped[str | None]
    curso: Mapped[str | None]
    unidade: Mapped[str | None]
    logradouro: Mapped[str | None]
    numero: Mapped[str | None]
    complemento: Mapped[str | None]
    bairro: Mapped[str | None]
    cidade: Mapped[str | None]
    uf: Mapped[str | None]
    cep: Mapped[str | None]
    validade_carteirinha: Mapped[date | None]
    situacao: Mapped[str]
    limite_emprestimos: Mapped[int]
    multas_pendentes: Mapped[Decimal]
    aceita_notificacoes: Mapped[bool]
    canal_preferido: Mapped[str | None]
    categorias_favoritas: Mapped[str | None]
    observacoes: Mapped[str | None]
    foto_url: Mapped[str | None]
    ultimo_acesso: Mapped[datetime | None]
    atualizado_em: Mapped[datetime | None]
    # documentos, contatos e preferências
    nome_social: Mapped[str | None]
    cpf: Mapped[str]
    rg: Mapped[str | None]
    orgao_emissor: Mapped[str | None]
    genero: Mapped[str | None]
    estado_civil: Mapped[str | None]
    nacionalidade: Mapped[str]
    naturalidade: Mapped[str | None]
    telefone: Mapped[str | None]
    celular: Mapped[str | None]
    email_alternativo: Mapped[str | None]
    escolaridade: Mapped[str | None]
    profissao: Mapped[str | None]
    empresa: Mapped[str | None]
    contato_emergencia: Mapped[str | None]
    telefone_emergencia: Mapped[str | None]
    necessidades_especiais: Mapped[str | None]
    idioma_preferido: Mapped[str]
    formato_preferido: Mapped[str | None]
    recebe_newsletter: Mapped[bool]
    termos_aceitos_em: Mapped[datetime | None]
    versao_termos: Mapped[str | None]
    origem_cadastro: Mapped[str | None]
    pontos_fidelidade: Mapped[int]
    nivel_fidelidade: Mapped[str | None]
    bloqueado_ate: Mapped[date | None]
    motivo_bloqueio: Mapped[str | None]
    senha_hash: Mapped[str | None]
    token_sessao: Mapped[str | None]
    preferencias_notificacao: Mapped[str | None]
    interesses: Mapped[str | None]
    ultimo_ip: Mapped[str | None]


class Emprestimo(Base):
    """Empréstimo com carregamento LAZY (sob demanda) do livro e do leitor."""

    __tablename__ = "emprestimo"

    id: Mapped[int] = mapped_column(primary_key=True)
    livro_id: Mapped[int] = mapped_column(ForeignKey("livro.id"))
    leitor_id: Mapped[int] = mapped_column(ForeignKey("leitor.id"))
    data_emprestimo: Mapped[datetime]
    data_prevista: Mapped[date]
    data_devolucao: Mapped[datetime | None]
    canal: Mapped[str]
    atendente: Mapped[str | None]
    renovacoes: Mapped[int]
    data_renovacao: Mapped[date | None]
    multa: Mapped[Decimal]
    avaliacao: Mapped[int | None]
    observacoes: Mapped[str | None]
    registrado_em: Mapped[datetime]
    # atendimento, exemplar, lembretes, multa e controle do registro
    protocolo: Mapped[str]
    unidade: Mapped[str]
    balcao: Mapped[int | None]
    terminal: Mapped[str | None]
    codigo_exemplar: Mapped[str]
    numero_exemplar: Mapped[int]
    estado_retirada: Mapped[str]
    estado_devolucao: Mapped[str | None]
    prazo_maximo: Mapped[date]
    renovacao_online: Mapped[bool]
    lembrete_enviado_em: Mapped[datetime | None]
    lembretes_enviados: Mapped[int]
    canal_lembrete: Mapped[str | None]
    dias_atraso: Mapped[int]
    multa_paga: Mapped[bool]
    data_pagamento_multa: Mapped[date | None]
    forma_pagamento: Mapped[str | None]
    desconto_multa: Mapped[Decimal]
    finalidade: Mapped[str]
    disciplina: Mapped[str | None]
    comentario_avaliacao: Mapped[str | None]
    ip_origem: Mapped[str | None]
    assinatura_termo: Mapped[str]
    atualizado_em: Mapped[datetime]
    versao: Mapped[int]

    livro: Mapped[Livro] = relationship(lazy="select")
    leitor: Mapped[Leitor] = relationship(lazy="select")


class EmprestimoEager(Base):
    """A mesma tabela emprestimo, com carregamento EAGER (antecipado) do livro e do leitor."""

    __table__ = Emprestimo.__table__

    livro: Mapped[Livro] = relationship(lazy="joined", viewonly=True)
    leitor: Mapped[Leitor] = relationship(lazy="joined", viewonly=True)

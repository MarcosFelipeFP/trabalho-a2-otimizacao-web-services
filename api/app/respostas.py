"""Resposta JSON serializada com orjson.

As rotas devolvem esta resposta pronta, sem passar pelo conversor genérico do FastAPI: assim
todas as versões de uma mesma consulta gastam o mesmo tempo para gerar o JSON, e a diferença
medida entre elas fica só no acesso aos dados. O cache guarda o JSON já serializado (bytes).
"""

from decimal import Decimal

import orjson
from fastapi import Response


def _converter(valor):
    # numeric do PostgreSQL chega como Decimal, que o orjson não serializa sozinho
    if isinstance(valor, Decimal):
        return float(valor)
    raise TypeError(f"tipo não serializável em JSON: {type(valor).__name__}")


def para_json(conteudo) -> bytes:
    return orjson.dumps(conteudo, default=_converter)


class RespostaJSON(Response):
    media_type = "application/json"

    def render(self, content) -> bytes:
        if isinstance(content, bytes):
            return content
        return para_json(content)

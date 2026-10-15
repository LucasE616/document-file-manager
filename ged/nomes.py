"""Metadados extraídos do nome do arquivo e do caminho da pasta.

São a segunda e a terceira fontes de metadados: valem para arquivos que não
aparecem em nenhum índice XML, e para completar registros cujo índice veio
com campos vazios. Os padrões vêm do perfil (ver perfil.py).
"""
from __future__ import annotations

import re

from . import perfil as perfis


def _limpar(grupos: dict[str, str | None]) -> dict[str, str]:
    return {nome: valor for nome, valor in grupos.items() if valor and not nome.startswith("_")}


def nome_base(nome_arquivo: str) -> str:
    """Só o nome, sem pasta — com barra de Windows ou de Linux."""
    return re.split(r"[\\/]", nome_arquivo or "")[-1]


def do_nome(nome_arquivo: str) -> tuple[str, dict[str, str]]:
    """Extrai tipo e campos do nome do arquivo.

    Devolve ("", {}) quando nenhum padrão reconhece o nome — o documento
    entra no catálogo mesmo assim, apenas sem esses campos.
    """
    base = nome_base(nome_arquivo)
    for tipo in perfis.ativo().tipos:
        for regex in tipo.padroes_nome:
            m = regex.match(base)
            if m:
                return tipo.chave, _limpar(m.groupdict())
    return "", {}


def do_caminho(caminho: str) -> dict[str, str]:
    """Extrai campos do caminho da pasta.

    Serve tanto para a pasta real onde o arquivo está quanto para o
    "Batch Location" gravado no XML, que aponta para a máquina de
    digitalização e frequentemente carrega o ano e o número que faltaram
    nos outros lugares.
    """
    campos: dict[str, str] = {}
    for regex in perfis.ativo().padroes_caminho:
        for m in regex.finditer(caminho or ""):
            for nome, valor in _limpar(m.groupdict()).items():
                campos.setdefault(nome, valor)
    return campos

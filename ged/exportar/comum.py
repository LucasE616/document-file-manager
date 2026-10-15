"""O que os relatórios de busca e de contagem têm em comum.

Todos registram no cabeçalho o que foi pedido — sem isso, uma lista de doze
documentos não diz, meses depois, se são todos os do período ou apenas os
que alguém escolheu.

CSV: separador ponto e vírgula e UTF-8 com BOM, que é o que faz o Excel em
português abrir com acentos e colunas corretos sem assistente. O contador
antigo usava vírgula, e as colunas não se separavam.

TXT: UTF-8 com BOM e quebras de linha do Windows, para o Bloco de Notas.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .. import NOME, __version__

SEPARADOR_CSV = ";"
LARGURA_TXT = 78
REGUA = "-" * LARGURA_TXT


def agora() -> str:
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M")


def assinatura() -> str:
    return f"{NOME} {__version__}"


def escopo_pasta(incluir_subpastas: bool) -> str:
    return "incluindo subpastas" if incluir_subpastas else "somente esta pasta"


def linha_rotulada(rotulo: str, valor: str, largura: int = 16) -> str:
    return f"{rotulo.ljust(largura, '.')} {valor}"


def gravar_txt(destino: Path | str, linhas: list[str]) -> Path:
    destino = Path(destino)
    # newline="" impede que o modo texto traduza de novo o \r\n já
    # explícito, o que deixaria o arquivo espaçado em dobro no Bloco de Notas.
    destino.write_text("\r\n".join(linhas) + "\r\n", encoding="utf-8-sig", newline="")
    return destino


def gravar_csv(destino: Path | str, cabecalho: list[str], linhas: list[list]) -> Path:
    destino = Path(destino)
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=SEPARADOR_CSV, quoting=csv.QUOTE_MINIMAL)
        escritor.writerow(cabecalho)
        for linha in linhas:
            escritor.writerow(["" if v is None else v for v in linha])
    return destino


def data_hora(valor: dt.datetime | None) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else ""

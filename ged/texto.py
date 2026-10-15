"""Normalização e formatação de texto.

Todo o acervo tem acentuação inconsistente: os XML vêm em Windows-1252, o
texto dos PDFs veio de reconhecimento óptico e os usuários digitam sem
acento. Buscar "municipio" precisa achar "MUNICÍPIO".

A formatação numérica é sempre a brasileira (1.234), em tela e nos
relatórios — antes o contador mostrava 1,234 e o GED 1.234.
"""
from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """Remove acentos e diferenças de caixa, para comparação de busca."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.casefold()


def contem(agulha: str, palheiro: str) -> bool:
    """Busca por substring, ignorando acento e caixa."""
    if not agulha:
        return True
    return normalizar(agulha) in normalizar(palheiro)


def formatar_inteiro(valor: int) -> str:
    """12345 -> '12.345' (separador de milhar brasileiro)."""
    return f"{valor:,}".replace(",", ".")


def formatar_bytes(valor: int) -> str:
    """Tamanho legível: 1536 -> '1,5 KB'."""
    tamanho = float(valor)
    for unidade in ("bytes", "KB", "MB", "GB"):
        if tamanho < 1024 or unidade == "GB":
            if unidade == "bytes":
                return f"{formatar_inteiro(int(tamanho))} bytes"
            return f"{tamanho:.1f} {unidade}".replace(".", ",")
        tamanho /= 1024
    return f"{valor} bytes"  # pragma: no cover


def plural(quantidade: int, singular: str, plural_: str | None = None) -> str:
    """'1 documento', '2 documentos', com o número já formatado."""
    palavra = singular if quantidade == 1 else (plural_ or singular + "s")
    return f"{formatar_inteiro(quantidade)} {palavra}"

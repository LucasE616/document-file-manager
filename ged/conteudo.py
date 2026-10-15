"""Texto dos PDFs, guardado em memória durante a sessão.

Numa pasta típica são cerca de 25 MB — o suficiente para que a primeira
busca por conteúdo pague o tempo de abrir os arquivos e todas as seguintes
respondam na hora, sem gravar nada em disco.

O texto é guardado já normalizado (sem acento, em minúsculas). Antes ele
era guardado cru e normalizado de novo a cada busca, o que fazia a
"segunda busca instantânea" refazer o trabalho sobre todo o texto lido.
"""
from __future__ import annotations

import threading
from pathlib import Path

from . import leitores
from .texto import normalizar


class CacheConteudo:
    """Texto normalizado dos PDFs já lidos nesta sessão."""

    def __init__(self) -> None:
        self._texto: dict[str, str] = {}
        self._falhas: dict[str, str] = {}
        self._trava = threading.Lock()

    def texto(self, caminho: Path | str) -> str:
        """Texto normalizado do PDF, lido na primeira chamada e reaproveitado depois."""
        chave = str(caminho)
        with self._trava:
            if chave in self._texto:
                return self._texto[chave]
        if Path(chave).suffix.lower() not in leitores.EXTENSOES_PDF:
            texto, erro = "", ""
        else:
            texto, erro = leitores.texto_pdf(chave)
        normalizado = normalizar(texto)
        with self._trava:
            self._texto[chave] = normalizado
            if erro:
                self._falhas[chave] = erro
        return normalizado

    def ja_lido(self, caminho: Path | str) -> bool:
        return str(caminho) in self._texto

    def tem_texto(self, caminho: Path | str) -> bool:
        """Falso para PDF que é só imagem — ou que falhou ao abrir."""
        return bool(self._texto.get(str(caminho), "").strip())

    @property
    def falhas(self) -> dict[str, str]:
        return dict(self._falhas)

    @property
    def lidos(self) -> int:
        return len(self._texto)

    def sem_texto(self, caminhos: list[str]) -> int:
        """Quantos, entre os já lidos, não tinham texto para procurar."""
        return sum(1 for c in caminhos if c in self._texto and not self._texto[c].strip())

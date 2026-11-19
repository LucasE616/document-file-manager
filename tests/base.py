"""Base dos testes: pasta temporária, perfil padrão garantido e utilidades.

Todo teste que mexe em arquivo herda de `TesteComPasta`:

- recebe uma pasta temporária nova em `self.pasta`, apagada no fim;
- roda com o perfil padrão — um `ged_perfil.json` na máquina de quem testa
  não muda o resultado;
- a "pasta do programa" aponta para dentro da pasta temporária, para que
  nenhum teste grave um `ged_perfil.json` de verdade no repositório.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ged import leitores, perfil as perfis

PDF_OK = leitores.pdf_disponivel()
IMAGEM_OK = leitores.imagem_disponivel()
sem_pdf = unittest.skipUnless(PDF_OK, "pypdfium2 não instalado")
sem_imagem = unittest.skipUnless(IMAGEM_OK, "Pillow não instalado")


class TesteComPasta(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)
        self.pasta_programa = self.pasta / "_programa"
        self.pasta_programa.mkdir()
        isolamento = mock.patch.object(perfis, "pasta_do_programa", return_value=self.pasta_programa)
        isolamento.start()
        self.addCleanup(isolamento.stop)
        perfis.definir(perfis.montar(perfis.PERFIL_PADRAO))
        self.addCleanup(perfis.definir, None)

    def perfil_com_tipo(self, rotulo: str, indices, palavras=()) -> str:
        """Cria um tipo no perfil em uso (gravado na pasta temporária) e devolve a chave."""
        perfil, chave = perfis.criar_tipo(perfis.ativo(), rotulo, indices, palavras)
        perfis.definir(perfis.salvar(perfil))
        return chave


def rodar_cli(*argumentos: str) -> tuple[int, str, str]:
    """Roda a linha de comando como o usuário rodaria. Devolve código, saída e erros."""
    from ged import cli

    saida, erro = io.StringIO(), io.StringIO()
    with mock.patch("ged.dependencias.garantir_no_terminal"), \
         contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = cli.principal(list(argumentos))
        except SystemExit as exc:
            codigo = exc.code
    return codigo, saida.getvalue(), erro.getvalue()

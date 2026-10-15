"""Base dos testes: pasta temporária e perfil padrão garantido."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ged import leitores, perfil as perfis

PDF_OK = leitores.pdf_disponivel()
IMAGEM_OK = leitores.imagem_disponivel()
sem_pdf = unittest.skipUnless(PDF_OK, "pypdfium2 não instalado")
sem_imagem = unittest.skipUnless(IMAGEM_OK, "Pillow não instalado")


class TesteComPasta(unittest.TestCase):
    def setUp(self) -> None:
        # Um ged_perfil.json na máquina de quem testa não pode mudar o resultado
        perfis.definir(perfis.montar(perfis.PERFIL_PADRAO))
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)

    def tearDown(self) -> None:
        perfis.definir(None)
        self._tmp.cleanup()

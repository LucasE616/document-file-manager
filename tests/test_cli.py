"""Linha de comando."""
import contextlib
import io
import unittest
from unittest import mock

from ged import cli
from tests.base import TesteComPasta, sem_pdf
from tests.gerador import gerar_pdf, indice_xml


class TestCli(TesteComPasta):
    def rodar(self, *argumentos):
        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch("ged.dependencias.garantir_no_terminal"), \
             contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            try:
                codigo = cli.principal(list(argumentos))
            except SystemExit as exc:
                codigo = exc.code
        return codigo, saida.getvalue(), erro.getvalue()

    def setUp(self):
        super().setUp()
        gerar_pdf(self.pasta / "despesa_2019_00001-261224-095339.pdf", 2)
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Favorecido": "CEMIG", "_arquivo": "despesa_2019_00001-261224-095339.pdf", "_paginas": 2}]))

    def test_buscar_e_exportar(self):
        destino = self.pasta / "r.xlsx"
        codigo, saida, _ = self.rodar("buscar", str(self.pasta), "--filtro", "Favorecido=cemig",
                                      "--tipo", "despesa", "--saida", str(destino))
        self.assertEqual(codigo, 0)
        self.assertIn("Resultado: 1 documento(s), 2 página(s)", saida)
        self.assertTrue(destino.exists())

    def test_forma_antiga_continua_valendo(self):
        codigo, saida, _ = self.rodar("--buscar", str(self.pasta), "--termo", "cemig")
        self.assertEqual(codigo, 0)
        self.assertIn("Resultado: 1", saida)

    def test_filtro_mal_escrito_e_recusado_com_mensagem(self):
        # Correção: antes quebrava com ValueError
        codigo, _, erro = self.rodar("buscar", str(self.pasta), "--filtro", "Favorecido")
        self.assertEqual(codigo, 2)
        self.assertIn("CAMPO=VALOR", erro)

    def test_tipo_desconhecido(self):
        codigo, _, erro = self.rodar("buscar", str(self.pasta), "--tipo", "contratos")
        self.assertEqual(codigo, 2)
        self.assertIn("não reconhecido", erro)

    def test_diretorio_inexistente(self):
        codigo, _, erro = self.rodar("contar", str(self.pasta / "nada"))
        self.assertEqual(codigo, 2)
        self.assertIn("não encontrado", erro)

    @sem_pdf
    def test_contar(self):
        destino = self.pasta / "c.txt"
        codigo, saida, _ = self.rodar("contar", str(self.pasta), "--tipos", "pdf,tif", "--saida", str(destino))
        self.assertEqual(codigo, 0)
        self.assertIn("Páginas: 2", saida)
        self.assertTrue(destino.exists())

    def test_tipos_invalidos(self):
        codigo, _, erro = self.rodar("contar", str(self.pasta), "--tipos", "docx")
        self.assertEqual(codigo, 2)
        self.assertIn("tipo desconhecido", erro)


if __name__ == "__main__":
    unittest.main()

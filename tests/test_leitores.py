"""Leitura de cada formato e estados de erro."""
import unittest

from ged import leitores
from tests.base import TesteComPasta, sem_imagem, sem_pdf
from tests.gerador import gerar_pdf


class TestLeitores(TesteComPasta):
    @sem_pdf
    def test_pdf_paginas_e_data_interna(self):
        caminho = gerar_pdf(self.pasta / "a.pdf", 4, criacao="20191129103000")
        leitura = leitores.ler(caminho)
        self.assertEqual((leitura.paginas, leitura.estado), (4, leitores.OK))
        self.assertEqual(leitura.data_interna.year, 2019)

    @sem_pdf
    def test_extensao_pdfa(self):
        caminho = gerar_pdf(self.pasta / "a.pdfa", 2)
        self.assertEqual(leitores.ler(caminho).paginas, 2)

    @sem_pdf
    def test_pdf_corrompido_e_vazio(self):
        (self.pasta / "ruim.pdf").write_bytes(b"%PDF-1.4 lixo")
        (self.pasta / "zero.pdf").write_bytes(b"")
        gerar_pdf(self.pasta / "sem_paginas.pdf", 0)
        self.assertEqual(leitores.ler(self.pasta / "ruim.pdf").estado, leitores.ERRO)
        self.assertEqual(leitores.ler(self.pasta / "zero.pdf").estado, leitores.ERRO)
        sem = leitores.ler(self.pasta / "sem_paginas.pdf")
        self.assertEqual((sem.estado, sem.paginas), (leitores.VAZIO, 0))

    @sem_pdf
    def test_arquivo_recusado_nao_fica_travado(self):
        # Correção: o PDFium deixava aberto o arquivo que recusava, e no
        # Windows ele não podia ser movido nem apagado
        for nome, conteudo in (("ruim.pdf", b"%PDF-1.4 lixo"), ("vazio.pdf", None)):
            caminho = self.pasta / nome
            if conteudo is None:
                gerar_pdf(caminho, 0)
            else:
                caminho.write_bytes(conteudo)
            leitores.ler(caminho)
            leitores.texto_pdf(caminho)
            leitores.miniatura_ppm(caminho)
            caminho.unlink()
            self.assertFalse(caminho.exists())

    def test_arquivo_sumiu(self):
        leitura = leitores.ler(self.pasta / "nao_existe.pdf")
        self.assertIn(leitura.estado, (leitores.INACESSIVEL, leitores.SEM_LEITOR))

    @sem_pdf
    def test_texto(self):
        caminho = gerar_pdf(self.pasta / "a.pdf", 2, texto="Prefeitura Municipal")
        texto, erro = leitores.texto_pdf(caminho)
        self.assertEqual(erro, "")
        self.assertEqual(texto.count("Prefeitura Municipal"), 2)

    @sem_imagem
    def test_tiff_multipagina_e_imagens(self):
        from PIL import Image

        quadros = [Image.new("RGB", (40, 40), cor) for cor in ("red", "green", "blue")]
        quadros[0].save(self.pasta / "scan.tif", save_all=True, append_images=quadros[1:])
        quadros[0].save(self.pasta / "foto.jpg")
        quadros[0].save(self.pasta / "foto.png")
        self.assertEqual(leitores.ler(self.pasta / "scan.tif").paginas, 3)
        self.assertEqual(leitores.ler(self.pasta / "foto.jpg", verificar_imagem=True).paginas, 1)
        self.assertEqual(leitores.ler(self.pasta / "foto.png").paginas, 1)

    @sem_imagem
    def test_imagem_danificada(self):
        (self.pasta / "ruim.png").write_bytes(b"\x89PNG\r\n\x1a\nlixo")
        self.assertEqual(leitores.ler(self.pasta / "ruim.png").estado, leitores.ERRO)

    def test_svg(self):
        (self.pasta / "a.svg").write_text('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>')
        (self.pasta / "b.svg").write_text("não é svg")
        self.assertEqual(leitores.ler(self.pasta / "a.svg").paginas, 1)
        self.assertEqual(leitores.ler(self.pasta / "b.svg").estado, leitores.ERRO)

    def test_conferencia_hash_e_pdfa(self):
        caminho = gerar_pdf(self.pasta / "a.pdf", 1, pdfa="2B")
        conferencia = leitores.conferir(caminho)
        self.assertEqual(conferencia.pdfa, "PDF/A-2B")
        self.assertEqual(len(conferencia.sha256), 64)
        self.assertEqual(leitores.conferir(gerar_pdf(self.pasta / "b.pdf", 1)).pdfa, "")

    @sem_pdf
    @sem_imagem
    def test_miniatura(self):
        dados = leitores.miniatura_ppm(gerar_pdf(self.pasta / "a.pdf", 1), 120)
        self.assertTrue(dados and dados.startswith(b"P6"))


if __name__ == "__main__":
    unittest.main()

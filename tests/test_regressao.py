"""Testes de regressão: cada teste prende um defeito que já existiu.

Convenção: o nome do teste diz o comportamento certo, e a docstring começa
com "Correção:" seguida do defeito como ele aparecia para o usuário. Se um
destes testes falhar, o defeito voltou. Os defeitos da interface gráfica
ficam em test_gui.py, que precisa de tela.
"""
import unittest
from unittest import mock

from ged import leitores
from tests.base import TesteComPasta, sem_imagem


def _maior_lado_convertido(chamada):
    """Roda `chamada` anotando o tamanho de toda imagem passada a Image.convert."""
    from PIL import Image

    tamanhos = []
    original = Image.Image.convert

    def espia(self, *args, **kwargs):
        tamanhos.append(max(self.size))
        return original(self, *args, **kwargs)

    with mock.patch.object(Image.Image, "convert", espia):
        resultado = chamada()
    return resultado, tamanhos


@sem_imagem
class TestMiniaturaDeImagemGrande(TesteComPasta):
    """Correção: a miniatura convertia a imagem inteira para RGB antes de reduzir.

    Uma planta de 500 megapixels ocupava 1,5 GB de memória para gerar uma
    miniatura de 230 pixels — e o limite de "bomba de descompressão" do
    Pillow foi desligado de propósito para essas plantas.
    """

    LARGURA = 230

    def gerar(self, nome, modo, tamanho=(3000, 2000), **opcoes):
        from PIL import Image

        caminho = self.pasta / nome
        Image.new(modo, tamanho, 255 if modo in ("1", "L") else (200, 120, 40)).save(caminho, **opcoes)
        return caminho

    def miniatura(self, caminho):
        dados, tamanhos = _maior_lado_convertido(lambda: leitores.miniatura_ppm(caminho, self.LARGURA))
        self.assertTrue(dados and dados.startswith(b"P6"), "a miniatura deve ser um PPM colorido")
        return tamanhos

    def test_png_colorido_reduz_antes_de_converter(self):
        tamanhos = self.miniatura(self.gerar("planta.png", "RGB"))
        self.assertLessEqual(max(tamanhos), self.LARGURA * 2)

    def test_jpeg_ja_e_decodificado_reduzido(self):
        tamanhos = self.miniatura(self.gerar("foto.jpg", "RGB", quality=70))
        self.assertLessEqual(max(tamanhos), self.LARGURA * 2)

    def test_tiff_em_tons_de_cinza_reduz_antes_de_converter(self):
        tamanhos = self.miniatura(self.gerar("escaneado.tif", "L", compression="tiff_lzw"))
        self.assertLessEqual(max(tamanhos), self.LARGURA * 2)

    def test_tiff_preto_e_branco_converte_para_8_bits_e_nao_para_rgb(self):
        # Reduzir o modo "1" direto sairia serrilhado: ele vira tons de cinza
        # (1 byte por pixel) antes de reduzir, nunca RGB (3 bytes) no tamanho cheio.
        from PIL import Image

        caminho = self.gerar("bitonal.tif", "1", compression="group4")
        modos = []
        original = Image.Image.convert

        def espia(self, modo=None, *args, **kwargs):
            if max(self.size) > 460:
                modos.append(modo)
            return original(self, modo, *args, **kwargs)

        with mock.patch.object(Image.Image, "convert", espia):
            self.assertIsNotNone(leitores.miniatura_ppm(caminho, self.LARGURA))
        self.assertEqual(modos, ["L"])

    def test_tiff_multipagina_usa_a_primeira(self):
        from PIL import Image

        caminho = self.pasta / "multi.tif"
        primeira = Image.new("RGB", (800, 600), (255, 0, 0))
        primeira.save(caminho, save_all=True, append_images=[Image.new("RGB", (800, 600), (0, 0, 255))])
        dados = leitores.miniatura_ppm(caminho, self.LARGURA)
        imagem = Image.open(__import__("io").BytesIO(dados))
        self.assertEqual(imagem.size[0], self.LARGURA)
        vermelho, _, azul = imagem.getpixel((10, 10))
        self.assertGreater(vermelho, azul)


if __name__ == "__main__":
    unittest.main()

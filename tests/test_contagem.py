"""Contagem e auditoria."""
import unittest
from datetime import date, datetime

from ged import catalogo as cat, contagem as ct, leitores
from tests.base import TesteComPasta, sem_imagem, sem_pdf
from tests.gerador import gerar_pdf, indice_xml


@sem_pdf
class TestContagem(TesteComPasta):
    def setUp(self):
        super().setUp()
        gerar_pdf(self.pasta / "indexado.pdf", 3)
        gerar_pdf(self.pasta / "a" / "igual.pdf", 2)
        gerar_pdf(self.pasta / "b" / "igual.pdf", 2)
        (self.pasta / "ruim.pdf").write_bytes(b"%PDF lixo")
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Numero": "1", "_arquivo": "indexado.pdf", "_paginas": 5},
            {"Numero": "2", "_arquivo": "sumiu.pdf", "_paginas": 1},
        ]))
        self.catalogo = cat.varrer(self.pasta)

    def categorias(self, resultado):
        return dict(resultado.problemas_por_categoria())

    def test_totais_e_problemas(self):
        r = ct.contar(self.catalogo, ct.OpcoesContagem())
        self.assertEqual(r.total_arquivos, 4)
        self.assertEqual(r.total_paginas, 3 + 2 + 2)
        self.assertEqual(r.total_erros, 1)
        problemas = self.categorias(r)
        self.assertEqual(problemas[ct.DIVERGENCIA], 1)
        self.assertEqual(problemas[ct.INDICE_SEM_ARQUIVO], 1)
        self.assertEqual(problemas[ct.ERRO_LEITURA], 1)
        self.assertNotIn(ct.CONTEUDO_IDENTICO, problemas)  # só na aprofundada

    def test_contagem_real_substitui_a_do_indice(self):
        ct.contar(self.catalogo, ct.OpcoesContagem())
        documento = next(d for d in self.catalogo.documentos if d.nome_arquivo == "indexado.pdf")
        self.assertEqual((documento.paginas_indice, documento.paginas_reais, documento.paginas), (5, 3, 3))
        self.assertTrue(documento.divergente)

    def test_aprofundada_acha_conteudo_identico(self):
        r = ct.contar(self.catalogo, ct.OpcoesContagem(aprofundada=True))
        self.assertEqual(self.categorias(r)[ct.CONTEUDO_IDENTICO], 1)
        self.assertEqual(len(r.hash_conjunto), 64)
        # o mesmo conjunto dá o mesmo hash
        self.assertEqual(ct.contar(self.catalogo, ct.OpcoesContagem(aprofundada=True)).hash_conjunto, r.hash_conjunto)

    def test_periodo_pela_data_de_criacao(self):
        for d in self.catalogo.documentos:
            d.data_criacao = datetime(2019, 6, 1) if d.nome_arquivo == "indexado.pdf" else datetime(2021, 1, 1)
        r = ct.contar(self.catalogo, ct.OpcoesContagem(data_de=date(2019, 1, 1), data_ate=date(2019, 12, 31)))
        self.assertEqual([d.nome_arquivo for d in r.itens], ["indexado.pdf"])
        self.assertEqual(r.fora_do_periodo, 3)

    def test_arquivo_sem_data_e_relatado_nao_descartado_em_silencio(self):
        # Correção: o contador ignorava calado arquivos de data ilegível
        for d in self.catalogo.documentos:
            d.data_criacao = None
        r = ct.contar(self.catalogo, ct.OpcoesContagem(data_de=date(2019, 1, 1)))
        self.assertEqual(self.categorias(r)[ct.DATA_ILEGIVEL], 4)

    def test_periodo_pela_data_interna(self):
        gerar_pdf(self.pasta / "datado.pdf", 1, criacao="20180305120000")
        catalogo = cat.varrer(self.pasta)
        r = ct.contar(catalogo, ct.OpcoesContagem(data_de=date(2018, 1, 1), data_ate=date(2018, 12, 31),
                                                  base_data=cat.BASE_INTERNA))
        self.assertEqual([d.nome_arquivo for d in r.itens], ["datado.pdf"])

    def test_agrupamentos(self):
        r = ct.contar(self.catalogo, ct.OpcoesContagem())
        for criterio in ct.AGRUPAMENTOS:
            with self.subTest(criterio):
                linhas = ct.agrupar(r, criterio)
                self.assertEqual(sum(l.arquivos for l in linhas), r.total_arquivos)
                self.assertEqual(sum(l.paginas for l in linhas), r.total_paginas)

    def test_cancelamento_marca_resultado_parcial(self):
        chamadas = iter(range(100))
        r = ct.contar(self.catalogo, ct.OpcoesContagem(), cancelado=lambda: next(chamadas) >= 2)
        self.assertTrue(r.cancelado)
        self.assertEqual(r.total_arquivos, 2)

    def test_tipo_nao_escolhido_fica_de_fora(self):
        (self.pasta / "x.svg").write_text("<svg/>")
        catalogo = cat.varrer(self.pasta)
        self.assertEqual(ct.contar(catalogo, ct.OpcoesContagem(extensoes={".svg"})).total_arquivos, 1)

    @sem_imagem
    def test_tiff_entra_na_contagem(self):
        from PIL import Image

        quadros = [Image.new("L", (20, 20), c) for c in (0, 128)]
        quadros[0].save(self.pasta / "scan.tiff", save_all=True, append_images=quadros[1:])
        catalogo = cat.varrer(self.pasta)
        r = ct.contar(catalogo, ct.OpcoesContagem(extensoes={".tif", ".tiff"}))
        self.assertEqual((r.total_arquivos, r.total_paginas), (1, 2))

    def test_paginas_faltantes_so_le_os_sem_indice(self):
        lidos = ct.ler_paginas_faltantes(self.catalogo)
        self.assertEqual(lidos, 3)  # indexado.pdf já tem páginas pelo índice
        estados = {d.nome_arquivo: d.estado for d in self.catalogo.documentos if d.localizado}
        self.assertEqual(estados["indexado.pdf"], "")
        self.assertEqual(estados["ruim.pdf"], leitores.ERRO)


if __name__ == "__main__":
    unittest.main()

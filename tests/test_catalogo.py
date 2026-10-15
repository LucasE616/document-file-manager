"""Varredura e vínculo entre índice e arquivo."""
import os
import unittest
from pathlib import Path
from unittest import mock

from ged import catalogo as cat
from tests.base import TesteComPasta
from tests.gerador import gerar_pdf, indice_xml


class TestVarredura(TesteComPasta):
    def test_homonimos_em_pastas_diferentes_nao_somem(self):
        # Correção: os PDFs eram indexados só pelo nome, e três
        # documento.pdf em pastas diferentes viravam um só.
        for sub in ("a", "b", "c"):
            gerar_pdf(self.pasta / sub / "documento.pdf", 2)
        catalogo = cat.varrer(self.pasta)
        self.assertEqual(catalogo.total_documentos, 3)
        self.assertEqual(len({d.caminho for d in catalogo.documentos}), 3)

    def test_reexportacao_nao_conta_em_dobro(self):
        # Correção: um PDF citado em dois XML entrava duas vezes
        gerar_pdf(self.pasta / "despesa_1-261224-095339.pdf", 1)
        xml = indice_xml([{"Favorecido": "CEMIG", "_arquivo": "despesa_1-261224-095339.pdf", "_paginas": 10}])
        (self.pasta / "lote.xml").write_bytes(xml)
        (self.pasta / "lote_reexportado.xml").write_bytes(xml)
        catalogo = cat.varrer(self.pasta)
        self.assertEqual(catalogo.total_documentos, 1)
        self.assertEqual(catalogo.total_paginas, 10)
        self.assertEqual(len(catalogo.registros_duplicados), 1)
        self.assertFalse(catalogo.registros_duplicados[0].campos_diferentes)

    def test_registro_vinculado_ao_arquivo_da_mesma_pasta(self):
        gerar_pdf(self.pasta / "lote1" / "doc.pdf", 1)
        gerar_pdf(self.pasta / "lote2" / "doc.pdf", 1)
        (self.pasta / "lote2" / "indice.xml").write_bytes(indice_xml([{"Numero": "7", "_arquivo": "doc.pdf"}]))
        catalogo = cat.varrer(self.pasta)
        indexado = next(d for d in catalogo.documentos if d.origem == cat.ORIGEM_XML)
        self.assertEqual(indexado.caminho.parent.name, "lote2")
        self.assertFalse(indexado.vinculo_ambiguo)
        self.assertEqual(catalogo.total_documentos, 2)

    def test_vinculo_incerto_e_sinalizado(self):
        gerar_pdf(self.pasta / "x" / "doc.pdf", 1)
        gerar_pdf(self.pasta / "y" / "doc.pdf", 1)
        (self.pasta / "indices" ).mkdir()
        (self.pasta / "indices" / "i.xml").write_bytes(indice_xml([{"Numero": "7", "_arquivo": "doc.pdf"}]))
        catalogo = cat.varrer(self.pasta)
        self.assertEqual(catalogo.vinculos_ambiguos, 1)

    def test_registro_sem_arquivo_e_arquivo_sem_registro(self):
        gerar_pdf(self.pasta / "solto.pdf", 2)
        (self.pasta / "i.xml").write_bytes(indice_xml([{"Numero": "1", "_arquivo": "sumiu.pdf", "_paginas": 3}]))
        catalogo = cat.varrer(self.pasta)
        self.assertEqual(catalogo.sem_arquivo, 1)
        self.assertEqual(catalogo.sem_indice, 1)

    def test_campos_completados_pelo_nome_sem_sobrescrever_o_xml(self):
        gerar_pdf(self.pasta / "despesa_2019_00042-261224-095339.pdf", 1)
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Numero": "42-A", "Ano": "", "_arquivo": "despesa_2019_00042-261224-095339.pdf"}]))
        documento = cat.varrer(self.pasta).documentos[0]
        self.assertEqual(documento.valor("Numero"), "42-A")
        self.assertEqual(documento.valor("Ano"), "2019")

    def test_arquivo_inacessivel_nao_derruba_a_varredura(self):
        # Correção: um stat() falhando interrompia a leitura inteira
        gerar_pdf(self.pasta / "a.pdf", 1)
        gerar_pdf(self.pasta / "b.pdf", 1)
        original = cat._info_arquivo

        def falha_em_b(caminho):
            if caminho.name == "b.pdf":
                raise PermissionError(13, "Acesso negado", str(caminho))
            return original(caminho)

        with mock.patch.object(cat, "_info_arquivo", falha_em_b):
            catalogo = cat.varrer(self.pasta)
        self.assertEqual(catalogo.total_documentos, 2)
        self.assertEqual(len(catalogo.inacessiveis), 1)

    def test_xml_ilegivel_e_registrado(self):
        gerar_pdf(self.pasta / "a.pdf", 1)
        (self.pasta / "ruim.xml").write_bytes(b"<root><document>")
        with mock.patch("ged.xml_parser.ler_indice", side_effect=ValueError("quebrado")):
            catalogo = cat.varrer(self.pasta)
        self.assertEqual(len(catalogo.xmls_com_falha), 1)
        self.assertEqual(catalogo.total_documentos, 1)

    def test_cancelamento(self):
        gerar_pdf(self.pasta / "a.pdf", 1)
        catalogo = cat.varrer(self.pasta, cancelado=lambda: True)
        self.assertTrue(catalogo.cancelado)

    def test_sem_subpastas(self):
        gerar_pdf(self.pasta / "raiz.pdf", 1)
        gerar_pdf(self.pasta / "sub" / "dentro.pdf", 1)
        self.assertEqual(cat.varrer(self.pasta, incluir_subpastas=False).total_documentos, 1)

    def test_diretorio_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            cat.varrer(self.pasta / "nao-existe")


class TestClassificacao(TesteComPasta):
    def test_tipos(self):
        raiz = Path(r"C:\Usuarios\Despesas da casa\ACERVO")
        casos = [
            ("pelo nome do arquivo", cat.Documento(tipo="licitacao"), "licitacao"),
            ("pelo Título do índice", cat.Documento(campos={"Título": "Despesa"}), "despesa"),
            ("Título 'Lei Ordinária'", cat.Documento(campos={"Titulo": "Lei Ordinária"}), "legislacao"),
            ("'Leilão' não é lei", cat.Documento(campos={"Titulo": "Leilão 03/2019"}), "outro"),
            ("pela pasta LEIS_2019", cat.Documento(caminho=raiz / "LEIS_2019" / "x.pdf"), "legislacao"),
            ("pasta mais próxima vence",
             cat.Documento(caminho=raiz / "DESPESAS" / "licitacoes_anexas" / "x.pdf"), "licitacao"),
            ("pasta acima da raiz não conta", cat.Documento(caminho=raiz / "2019" / "x.pdf"), "outro"),
        ]
        for descricao, documento, esperado in casos:
            with self.subTest(descricao):
                self.assertEqual(cat.classificar(documento, raiz), esperado)

    def test_outro_tipo_por_indices(self):
        gerar_pdf(self.pasta / "a.pdf", 1)
        gerar_pdf(self.pasta / "b.pdf", 1)
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Contratado": "ACME", "_arquivo": "a.pdf"}, {"Favorecido": "CEMIG", "_arquivo": "b.pdf"}]))
        catalogo = cat.varrer(self.pasta)
        recorte = cat.subcatalogo_por_indices(catalogo, ["Contratado"])
        self.assertEqual([d.nome_arquivo for d in recorte.documentos], ["a.pdf"])


if __name__ == "__main__":
    unittest.main()

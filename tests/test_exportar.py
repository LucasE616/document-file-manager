"""Relatórios TXT, CSV e XLSX."""
import csv
import unittest
import zipfile
from xml.etree import ElementTree as ET

from ged import catalogo as cat, contagem as ct
from ged.busca import Criterios, buscar
from ged.exportar import busca as exp_busca, contagem as exp_contagem
from ged.exportar.xlsx import Planilha, escrever_xlsx
from tests.base import TesteComPasta
from tests.gerador import gerar_pdf, indice_xml

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def ler_xlsx(caminho):
    """Lê o .xlsx de volta com a biblioteca padrão: {aba: [[valores]]}."""
    with zipfile.ZipFile(caminho) as zf:
        livro = ET.fromstring(zf.read("xl/workbook.xml"))
        nomes = [s.get("name") for s in livro.find("m:sheets", NS)]
        abas = {}
        for i, nome in enumerate(nomes, 1):
            folha = ET.fromstring(zf.read(f"xl/worksheets/sheet{i}.xml"))
            linhas = []
            for linha in folha.iter(f"{{{NS['m']}}}row"):
                valores = []
                for c in linha:
                    t = c.find("m:is/m:t", NS)
                    v = c.find("m:v", NS)
                    valores.append(t.text if t is not None else (v.text if v is not None else None))
                linhas.append(valores)
            abas[nome] = linhas
    return abas


class TestXlsx(TesteComPasta):
    def test_escreve_e_le_de_volta(self):
        destino = escrever_xlsx(self.pasta / "t.xlsx", [
            Planilha("Dados: 1/2", [["Nome", "Páginas"], ["São João & <Cia>", 12], ["x\x01y", None]]),
            Planilha("Dados: 1/2", [["repetida"]]),
        ])
        abas = ler_xlsx(destino)
        self.assertEqual(list(abas), ["Dados_ 1_2", "Dados_ 1_2 (2)"])
        self.assertEqual(abas["Dados_ 1_2"][1], ["São João & <Cia>", "12"])
        self.assertEqual(abas["Dados_ 1_2"][2], ["xy"])


class TestRelatorios(TesteComPasta):
    def setUp(self):
        super().setUp()
        gerar_pdf(self.pasta / "d1.pdf", 2)
        gerar_pdf(self.pasta / "d2.pdf", 3)
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Favorecido": "Prefeitura; Câmara", "_arquivo": "d1.pdf", "_paginas": 2},
            {"Favorecido": "CEMIG", "_arquivo": "sumiu.pdf", "_paginas": 1},
        ]))
        self.catalogo = cat.varrer(self.pasta)

    def test_busca_csv_com_ponto_e_virgula(self):
        criterios = Criterios(filtros={"Favorecido": "prefeitura"})
        resultado = buscar(self.catalogo, criterios)
        destino = exp_busca.exportar(self.pasta / "b.csv", self.catalogo, resultado, criterios)
        bruto = destino.read_bytes()
        self.assertTrue(bruto.startswith(b"\xef\xbb\xbf"))  # BOM para o Excel
        linhas = list(csv.reader(destino.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        self.assertEqual(linhas[0][0], "Favorecido")
        self.assertEqual(linhas[1][0], "Prefeitura; Câmara")

    def test_busca_txt_e_xlsx(self):
        criterios = Criterios()
        resultado = buscar(self.catalogo, criterios)
        txt = exp_busca.exportar(self.pasta / "b.txt", self.catalogo, resultado, criterios)
        conteudo = txt.read_text(encoding="utf-8-sig")
        self.assertIn("RELATÓRIO DE BUSCA", conteudo)
        self.assertIn("arquivo não localizado", conteudo)
        self.assertNotIn(b"\r\r\n", txt.read_bytes())
        abas = ler_xlsx(exp_busca.exportar(self.pasta / "b.xlsx", self.catalogo, resultado, criterios))
        self.assertEqual(list(abas), ["Resumo", "Resultado"])
        self.assertEqual(len(abas["Resultado"]), 1 + resultado.total_documentos)

    def test_formato_desconhecido(self):
        with self.assertRaises(ValueError):
            exp_busca.exportar(self.pasta / "b.doc", self.catalogo, buscar(self.catalogo, Criterios()), Criterios())

    @unittest.skipUnless(ct.leitores.pdf_disponivel(), "pypdfium2 não instalado")
    def test_contagem_nos_tres_formatos(self):
        resultado = ct.contar(self.catalogo, ct.OpcoesContagem(aprofundada=True))
        csv_destino = exp_contagem.exportar(self.pasta / "c.csv", resultado)
        linhas = list(csv.reader(csv_destino.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        # Correção: o CSV agora é só a tabela, sem o resumo misturado no topo
        self.assertEqual(linhas[0][0], "Arquivo")
        self.assertEqual(len(linhas), 1 + resultado.total_arquivos)

        txt = exp_contagem.exportar(self.pasta / "c.txt", resultado).read_text(encoding="utf-8-sig")
        self.assertIn("RELATÓRIO DE CONTAGEM E AUDITORIA", txt)
        self.assertIn("Hash do conjunto", txt)
        self.assertIn(ct.INDICE_SEM_ARQUIVO, txt)

        abas = ler_xlsx(exp_contagem.exportar(self.pasta / "c.xlsx", resultado))
        self.assertIn("Arquivos", abas)
        self.assertIn("Problemas", abas)
        self.assertIn("Por PDF-A declarado", abas)


if __name__ == "__main__":
    unittest.main()

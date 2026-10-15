"""XML, nomes de arquivo, caminhos e perfil."""
import json
import unittest
from pathlib import Path

from ged import nomes, perfil as perfis, xml_parser
from ged.texto import contem, formatar_bytes, formatar_inteiro
from tests.base import TesteComPasta
from tests.gerador import indice_xml

RAIZ = Path(__file__).resolve().parent.parent


class TestTexto(unittest.TestCase):
    def test_sem_acento_e_sem_caixa(self):
        for agulha, palheiro in [("municipio", "MUNICÍPIO"), ("SAO", "São"), ("agua", "Água")]:
            self.assertTrue(contem(agulha, palheiro))

    def test_formatacao_brasileira(self):
        self.assertEqual(formatar_inteiro(1234567), "1.234.567")
        self.assertEqual(formatar_bytes(1536), "1,5 KB")


class TestXML(TesteComPasta):
    def _gravar(self, conteudo: bytes, nome="indice.xml") -> Path:
        caminho = self.pasta / nome
        caminho.write_bytes(conteudo)
        return caminho

    def test_cp1252_declarado_como_utf8(self):
        caminho = self._gravar(indice_xml([{"Favorecido": "Prefeitura de São João", "_arquivo": "a.pdf", "_paginas": 3}],
                                          encoding="cp1252"))
        registros, tolerante = xml_parser.ler_indice(caminho)
        self.assertFalse(tolerante)
        self.assertEqual(registros[0].campos["Favorecido"], "Prefeitura de São João")
        self.assertEqual(registros[0].nome_arquivo, "a.pdf")
        self.assertEqual(registros[0].paginas, 3)

    def test_valor_truncado_usa_modo_tolerante(self):
        texto = ('<?xml version="1.0" encoding="utf-8"?><root><document>'
                 '<field level="document" name="Historico" value="Pagamento de energia &amp; agua'
                 '<field level="system" name="Document File Name" value="x.pdf"/></document></root>')
        registros, tolerante = xml_parser.ler_indice(self._gravar(texto.encode("utf-8")))
        self.assertTrue(tolerante)
        self.assertEqual(registros[0].nome_arquivo, "x.pdf")
        self.assertTrue(registros[0].campos["Historico"].startswith("Pagamento de energia & agua"))

    def test_lixo_em_volta_e_documentos_aninhados(self):
        texto = ('"""\n?<?xml version="1.0"?><root><lote><document>'
                 '<field level="document" name="Numero" value="12"/></document></lote></root>lixo')
        registros, _ = xml_parser.ler_indice(self._gravar(texto.encode("utf-8")))
        self.assertEqual(registros[0].campos, {"Numero": "12"})

    def test_nome_com_caminho_da_estacao(self):
        texto = ('<root><document><field level="system" name="Document File Name" '
                 'value="C:\\Kodak\\lote 3\\doc.pdf"/></document></root>')
        registros, _ = xml_parser.ler_indice(self._gravar(texto.encode("utf-8")))
        self.assertEqual(registros[0].nome_arquivo, "doc.pdf")


class TestNomes(TesteComPasta):
    def test_nome_do_arquivo(self):
        casos = [
            ("Despesa_2019_06953-261224-095339.pdf", "despesa", {"Ano": "2019", "Numero": "06953"}),
            ("Despesa_06953-261224-095339.pdf", "despesa", {"Numero": "06953"}),
            ("licitacao_058-2015-06112025-1726.pdfa", "licitacao", {"Numero": "058-2015"}),
            ("lei_1234_2015-010101-000000.pdf", "legislacao", {"Tipo": "lei", "Numero": "1234", "Ano": "2015"}),
            ("qualquer.pdf", "", {}),
        ]
        for arquivo, tipo_esperado, esperados in casos:
            with self.subTest(arquivo=arquivo):
                tipo, campos = nomes.do_nome(arquivo)
                self.assertEqual(tipo, tipo_esperado)
                for chave, valor in esperados.items():
                    self.assertEqual(campos.get(chave), valor)

    def test_caminho_da_pasta(self):
        campos = nomes.do_caminho(r"C:\PaperCapture\exportados\licitacao\2017\licitacao_098_76")
        self.assertEqual(campos, {"Numero": "098", "Ano": "2017"})
        self.assertEqual(nomes.do_caminho(r"D:\Kodak\2019\DESPESAS\DESPESAS_2019_121_NOV")["Ano"], "2019")


class TestPerfil(TesteComPasta):
    def test_exemplo_igual_ao_padrao(self):
        exemplo = json.loads((RAIZ / "exemplos" / "ged_perfil.json").read_text(encoding="utf-8"))
        self.assertEqual(exemplo, perfis.PERFIL_PADRAO)

    def test_perfil_personalizado(self):
        arquivo = self.pasta / "perfil.json"
        arquivo.write_text(json.dumps({
            "tipos": [{"chave": "contrato", "rotulo": "Contratos", "pistas": "contrat",
                       "padroes_nome": [r"^contrato[_-](?P<Numero>\d+)"]}],
        }), encoding="utf-8")
        perfis.definir(perfis.carregar_arquivo(arquivo))
        self.assertEqual(nomes.do_nome("contrato_77.pdf"), ("contrato", {"Numero": "77"}))
        self.assertEqual(nomes.do_nome("despesa_1-261224-095339.pdf"), ("", {}))

    def test_perfil_invalido_explica_o_erro(self):
        with self.assertRaisesRegex(perfis.ErroPerfil, r"tipos\[0\]\.padroes_nome\[0\]"):
            perfis.montar({"tipos": [{"chave": "x", "rotulo": "X", "padroes_nome": ["(sem fechar"]}]})
        with self.assertRaises(perfis.ErroPerfil):
            perfis.montar({"tipos": [{"chave": "outro", "rotulo": "Outro"}]})


if __name__ == "__main__":
    unittest.main()

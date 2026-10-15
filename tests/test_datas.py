import unittest
from datetime import date, datetime

from ged import datas


class TestDatas(unittest.TestCase):
    def test_formatos_diferentes_se_encontram(self):
        # O acervo grava a mesma informação em formatos diferentes, e o
        # usuário digita num terceiro. Todos precisam se encontrar.
        casos = [
            ("29/11/2019", "2019-11-29", True),
            ("2019-11-29", "2019-11-29", True),
            ("29-11-2019", "2019-11-29", True),
            ("29/11/2019", "29-11-2019", True),
            ("11/2019", "2019-11-29", True),
            ("2019", "2019-11-29", True),
            ("2019", "01-11-2019", True),
            ("29/11/19", "2019-11-29", True),
            ("12/2019", "2019-11-29", False),
            ("29/11/2019", "2019-11-28", False),
            ("2020", "2019-11-29", False),
        ]
        for consulta, valor, esperado in casos:
            with self.subTest(consulta=consulta, valor=valor):
                self.assertIs(datas.casa_como_data(consulta, valor), esperado)

    def test_numeros_nao_viram_datas(self):
        # Correção: o strptime aceitava 1 dígito em %d/%m e transformava
        # números de empenho em datas (1012019 -> 09/01/1012).
        for valor in ["1012019", "3112020", "2019111", "101.0", "1100.07", "1.0", "CEMIG", "12030", "11"]:
            with self.subTest(valor=valor):
                self.assertIsNone(datas.interpretar(valor))

    def test_hora_colada_e_ignorada(self):
        self.assertEqual(datas.interpretar("2019-11-29 00:00:00"), date(2019, 11, 29))
        self.assertEqual(datas.interpretar("2019-11-29T10:30"), date(2019, 11, 29))

    def test_periodos(self):
        casos = [
            ("2019", "2019", "2019-06-15", True),
            ("01/11/2019", "30/11/2019", "2019-11-29", True),
            ("01/11/2019", "30/11/2019", "2019-12-01", False),
            ("11/2019", "11/2019", "2019-11-30", True),
            ("02/2020", "02/2020", "2020-02-29", True),
            ("", "2019", "2018-05-04", True),
            ("2020", "", "2019-11-29", False),
        ]
        for de, ate, valor, esperado in casos:
            with self.subTest(de=de, ate=ate, valor=valor):
                alvo = datas.interpretar(valor)
                inicio = datas.limite_periodo(de, inicio=True)
                fim = datas.limite_periodo(ate, inicio=False)
                dentro = (inicio is None or alvo >= inicio) and (fim is None or alvo <= fim)
                self.assertIs(dentro, esperado)

    def test_periodo_invalido_e_detectado(self):
        self.assertTrue(datas.periodo_valido(""))
        self.assertTrue(datas.periodo_valido("11/2019"))
        self.assertFalse(datas.periodo_valido("novembro"))
        self.assertFalse(datas.periodo_valido("31/02/2019"))

    def test_campo_de_data_pelo_conteudo(self):
        self.assertTrue(datas.parece_campo_de_data(["2019-11-29", "01-11-2019", "2019-12-02"], "Data de Pagto"))
        self.assertTrue(datas.parece_campo_de_data(["2019-11-29", "01-11-2019", "2019-12-02"], "Vencto"))
        self.assertFalse(datas.parece_campo_de_data(["CEMIG", "COPASA", "2019-01-01"], "Favorecido"))

    def test_oito_digitos_so_com_nome_de_data(self):
        # Correção: empenhos de 8 dígitos viravam "campo de data"
        empenhos = ["12052019", "01022020", "15032021"]
        self.assertFalse(datas.parece_campo_de_data(empenhos, "Empenho"))
        self.assertTrue(datas.parece_campo_de_data(empenhos, "Data Empenho"))

    def test_amostra_pequena_exige_nome_de_data(self):
        # Correção: min(minimo, 1) deixava um único valor decidir
        self.assertFalse(datas.parece_campo_de_data(["2019-01-01"], "Observação"))
        self.assertTrue(datas.parece_campo_de_data(["2019-01-01"], "Data"))

    def test_data_interna_do_pdf(self):
        self.assertEqual(datas.interpretar_data_pdf("D:20191129103000-03'00'"), datetime(2019, 11, 29, 10, 30))
        self.assertEqual(datas.interpretar_data_pdf("D:2019"), datetime(2019, 1, 1))
        self.assertIsNone(datas.interpretar_data_pdf(""))
        self.assertIsNone(datas.interpretar_data_pdf("lixo"))


if __name__ == "__main__":
    unittest.main()

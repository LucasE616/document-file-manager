"""Busca: filtros em E, texto livre em OU, períodos e conteúdo."""
import unittest
from datetime import datetime

from ged import catalogo as cat
from ged.busca import Criterios, a_ler_para_conteudo, buscar
from ged.conteudo import CacheConteudo
from tests.base import TesteComPasta, sem_pdf
from tests.gerador import gerar_pdf, indice_xml


class TestBusca(TesteComPasta):
    def setUp(self):
        super().setUp()
        gerar_pdf(self.pasta / "d1.pdf", 2, texto="Nota fiscal da CEMIG")
        gerar_pdf(self.pasta / "d2.pdf", 3, texto="Contrato de limpeza urbana")
        gerar_pdf(self.pasta / "d3.pdf", 1, texto="Sem relacao")
        (self.pasta / "i.xml").write_bytes(indice_xml([
            {"Favorecido": "CEMIG Distribuição", "Data de Pagto": "2019-11-29", "Empenho": "12052019",
             "_arquivo": "d1.pdf", "_paginas": 2},
            {"Favorecido": "Limpa Tudo Ltda", "Data de Pagto": "05-12-2019", "Empenho": "01022020",
             "_arquivo": "d2.pdf", "_paginas": 3},
            {"Favorecido": "COPASA", "Data de Pagto": "2020-01-10", "Empenho": "15032021",
             "_arquivo": "d3.pdf", "_paginas": 1},
        ]))
        self.catalogo = cat.varrer(self.pasta)

    def nomes(self, resultado):
        return sorted(d.nome_arquivo for d in resultado.documentos)

    def test_campos_de_data_detectados(self):
        self.assertEqual(self.catalogo.campos_data, ["Data de Pagto"])

    def test_filtro_por_campo_sem_acento(self):
        r = buscar(self.catalogo, Criterios(filtros={"Favorecido": "distribuicao"}))
        self.assertEqual(self.nomes(r), ["d1.pdf"])

    def test_filtro_de_data_aceita_qualquer_formato(self):
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(filtros={"Data de Pagto": "12/2019"}))), ["d2.pdf"])
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(filtros={"Data de Pagto": "2019"}))),
                         ["d1.pdf", "d2.pdf"])

    def test_campo_que_nao_e_data_compara_como_texto(self):
        # Correção: "05/2019" no Empenho casava com 12052019 como se fosse data
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(filtros={"Empenho": "05/2019"}))), [])
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(filtros={"Empenho": "0520"}))), ["d1.pdf"])

    def test_periodo_do_indice(self):
        r = buscar(self.catalogo, Criterios(indice_de="11/2019", indice_ate="12/2019"))
        self.assertEqual(self.nomes(r), ["d1.pdf", "d2.pdf"])

    def test_periodo_do_arquivo_por_base(self):
        for d in self.catalogo.documentos:
            d.data_criacao = datetime(2026, 1, 1)
            d.data_modificacao = datetime(2020, 5, 5)
        self.assertEqual(len(buscar(self.catalogo, Criterios(arquivo_de="2026")).documentos), 3)
        self.assertEqual(len(buscar(self.catalogo, Criterios(arquivo_de="2026", base_data_arquivo="modificacao")).documentos), 0)

    def test_texto_livre_no_nome_e_no_indice(self):
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(termo="copasa"))), ["d3.pdf"])
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(termo="d2"))), ["d2.pdf"])
        self.assertEqual(self.nomes(buscar(self.catalogo, Criterios(termo="copasa", escopo_indice=False))), [])

    @sem_pdf
    def test_conteudo_amplia_e_so_abre_o_necessario(self):
        cache = CacheConteudo()
        criterios = Criterios(termo="limpeza urbana", escopo_conteudo=True)
        self.assertEqual(len(a_ler_para_conteudo(self.catalogo, criterios, cache)), 3)
        r = buscar(self.catalogo, criterios, cache=cache)
        self.assertEqual(self.nomes(r), ["d2.pdf"])
        self.assertEqual(r.achados_por_conteudo, 1)
        # Segunda busca: tudo já em memória, nada a abrir
        self.assertEqual(a_ler_para_conteudo(self.catalogo, criterios, cache), [])

    @sem_pdf
    def test_conteudo_casa_com_o_que_ja_casou_pelo_indice(self):
        r = buscar(self.catalogo, Criterios(termo="cemig", escopo_conteudo=True), cache=CacheConteudo())
        self.assertEqual(self.nomes(r), ["d1.pdf"])
        self.assertEqual(r.lidos_para_conteudo, 2)  # d1 casou pelo índice e não foi aberto


if __name__ == "__main__":
    unittest.main()

"""Tipos documentais criados pelo usuário: perfil, enquadramento, busca e linha de comando."""
import json
import os
import unittest
from unittest import mock

from ged import busca, catalogo as cat, perfil as perfis
from tests.base import TesteComPasta, rodar_cli
from tests.gerador import gerar_pdf, indice_xml

INDICES_CONTRATO = ["Contratado", "Objeto", "Vigência"]


def montar_acervo(pasta):
    """Pasta com dois contratos, uma despesa e um documento sem tipo."""
    for nome in ("c1.pdf", "c2.pdf", "despesa_2019_00001-261224-095339.pdf", "solto.pdf"):
        gerar_pdf(pasta / nome, 1)
    (pasta / "i.xml").write_bytes(indice_xml([
        {"Contratado": "ACME Ltda", "Objeto": "Limpeza", "Vigência": "01/01/2020", "Valor": "10",
         "_arquivo": "c1.pdf", "_paginas": 1},
        {"Contratado": "Beta SA", "Objeto": "Vigilância", "_arquivo": "c2.pdf", "_paginas": 1},
        {"Favorecido": "CEMIG", "Objeto": "Energia", "_arquivo": "despesa_2019_00001-261224-095339.pdf",
         "_paginas": 1},
        {"Assunto": "Ofício", "_arquivo": "solto.pdf", "_paginas": 1},
    ]))


class TestCriarTipo(TesteComPasta):
    def test_cria_com_chave_e_indices(self):
        perfil, chave = perfis.criar_tipo(perfis.ativo(), "Contratos Aditivos", "Contratado, Objeto ,Objeto")
        self.assertEqual(chave, "contratos_aditivos")
        tipo = perfil.tipo(chave)
        self.assertEqual(tipo.rotulo, "Contratos Aditivos")
        self.assertEqual(tipo.indices, ["Contratado", "Objeto"])  # repetido entra uma vez só
        self.assertEqual(len(perfil.tipos), 4)

    def test_perfil_original_nao_e_alterado(self):
        original = perfis.ativo()
        perfis.criar_tipo(original, "Contratos", INDICES_CONTRATO)
        self.assertEqual(len(original.tipos), 3)
        self.assertEqual(len(original.dados["tipos"]), 3)

    def test_validacoes(self):
        perfil = perfis.ativo()
        casos = {
            "nome vazio": ("   ", ["A"]),
            "sem índice": ("Contratos", ""),
            "nome repetido, sem acento e em minúsculas": ("licitacoes", ["A"]),
            "nome reservado": ("Outro tipo de documento", ["A"]),
        }
        for descricao, (rotulo, indices) in casos.items():
            with self.subTest(descricao), self.assertRaises(perfis.ErroPerfil):
                perfis.criar_tipo(perfil, rotulo, indices)

    def test_chave_unica_e_nunca_reservada(self):
        self.assertEqual(perfis.chave_para("Despesas", {"despesas"}), "despesas_2")
        self.assertEqual(perfis.chave_para("Despesas", {"despesas", "despesas_2"}), "despesas_3")
        self.assertEqual(perfis.chave_para("Outro"), "tipo_outro")
        self.assertEqual(perfis.chave_para("!!!"), "tipo")
        self.assertEqual(perfis.chave_para("Licitação Pública"), "licitacao_publica")

    def test_excluir(self):
        perfil, chave = perfis.criar_tipo(perfis.ativo(), "Contratos", INDICES_CONTRATO)
        sem = perfis.excluir_tipo(perfil, chave)
        self.assertIsNone(sem.tipo(chave))
        self.assertEqual(len(sem.tipos), 3)
        with self.assertRaises(perfis.ErroPerfil):
            perfis.excluir_tipo(sem, chave)


class TestPalavrasChave(unittest.TestCase):
    def pistas(self, *palavras):
        import re

        return re.compile(perfis.pistas_das_palavras(list(palavras)))

    def test_comeco_de_palavra_sem_acento(self):
        regex = self.pistas("Contrato", "Ofício")
        self.assertTrue(regex.search("contratos 2019"))
        self.assertTrue(regex.search("oficios recebidos"))
        self.assertFalse(regex.search("subcontratos"))

    def test_palavra_curta_precisa_ser_inteira(self):
        regex = self.pistas("ata")
        self.assertTrue(regex.search("ata de reuniao"))
        self.assertFalse(regex.search("atas"))
        self.assertFalse(regex.search("contratada"))

    def test_caracteres_especiais_nao_quebram_a_expressao(self):
        self.assertTrue(self.pistas("c++ (v2)").search("c++ (v2) manual"))

    def test_sem_palavras_nao_casa_nada(self):
        self.assertEqual(perfis.pistas_das_palavras(["", "  "]), "")


class TestGravarPerfil(TesteComPasta):
    def test_grava_ao_lado_do_programa_e_le_de_volta(self):
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO, "contrato")
        arquivo = self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL
        self.assertTrue(arquivo.is_file())
        self.assertEqual(perfis.ativo().origem, str(arquivo))

        perfis.definir(None)  # força ler do disco, como na próxima abertura
        relido = perfis.ativo()
        self.assertEqual(relido.tipo(chave).indices, INDICES_CONTRATO)
        self.assertEqual(relido.tipo(chave).palavras, ["contrato"])
        self.assertEqual([t.chave for t in relido.tipos][:3], ["despesa", "licitacao", "legislacao"])

    def test_json_legivel_e_com_acentos(self):
        self.perfil_com_tipo("Licenças", ["Requerente"])
        texto = (self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL).read_text(encoding="utf-8")
        self.assertIn('"rotulo": "Licenças"', texto)
        json.loads(texto)

    def test_grava_no_proprio_arquivo_do_perfil(self):
        outro = self.pasta / "meu_perfil.json"
        perfil = perfis.salvar(perfis.ativo(), outro)
        perfil, _ = perfis.criar_tipo(perfil, "Contratos", INDICES_CONTRATO)
        perfis.salvar(perfil)
        self.assertEqual(len(perfis.carregar_arquivo(outro).tipos), 4)
        self.assertFalse((self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL).exists())

    def test_falha_ao_gravar_nao_deixa_arquivo_pela_metade(self):
        arquivo = self.pasta / "p.json"
        perfis.salvar(perfis.ativo(), arquivo)
        antes = arquivo.read_bytes()
        perfil, _ = perfis.criar_tipo(perfis.carregar_arquivo(arquivo), "Contratos", ["A"])
        with mock.patch.object(os, "replace", side_effect=PermissionError(13, "sem permissão")):
            with self.assertRaises(perfis.ErroPerfil):
                perfis.salvar(perfil)
        self.assertEqual(arquivo.read_bytes(), antes)
        self.assertEqual([p.name for p in self.pasta.iterdir() if p.suffix == ".tmp"], [])

    def test_indices_invalidos_no_json(self):
        with self.assertRaises(perfis.ErroPerfil):
            perfis.montar({"tipos": [{"chave": "x", "rotulo": "X", "indices": "A,B"}]})


class TestEnquadramento(TesteComPasta):
    def setUp(self):
        super().setUp()
        montar_acervo(self.pasta)

    def grupos(self):
        catalogo = cat.varrer(self.pasta)
        grupos, sem_tipo = cat.agrupar_por_tipo(catalogo)
        return catalogo, {g.chave: g for g in grupos}, sem_tipo

    def test_sem_o_tipo_contratos_ficam_em_outro(self):
        _, grupos, sem_tipo = self.grupos()
        self.assertEqual(sem_tipo, 3)
        self.assertNotIn("contratos", grupos)

    def test_documentos_enquadrados_pelos_indices(self):
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        _, grupos, sem_tipo = self.grupos()
        nomes = sorted(d.nome_arquivo for d in grupos[chave].documentos)
        self.assertEqual(nomes, ["c1.pdf", "c2.pdf"])
        # A despesa tem "Objeto", mas o padrão do nome é pista mais forte
        self.assertEqual(len(grupos["despesa"].documentos), 1)
        self.assertEqual(sem_tipo, 1)

    def test_indices_declarados_viram_as_colunas(self):
        chave = self.perfil_com_tipo("Contratos", ["vigencia", "CONTRATADO", "Fiscal"])
        catalogo, grupos, _ = self.grupos()
        # Casados com a grafia do XML, na ordem declarada; "Valor" fica de fora
        self.assertEqual(grupos[chave].vocabulario, ["Vigência", "Contratado"])
        self.assertEqual(grupos[chave].indices_ausentes, ["Fiscal"])
        recorte = cat.subcatalogo(catalogo, grupos[chave])
        self.assertEqual(recorte.vocabulario, ["Vigência", "Contratado"])
        self.assertEqual(recorte.tipo_ativo, "Contratos")

    def test_tipos_sem_indices_continuam_com_todos_os_campos(self):
        self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        _, grupos, _ = self.grupos()
        self.assertEqual(grupos["despesa"].vocabulario, ["Objeto", "Favorecido", "Ano", "Numero"])

    def test_campos_do_nome_do_arquivo_nao_enquadram(self):
        # "Ano" vem do nome do arquivo, não do XML: não pode puxar a despesa
        chave = self.perfil_com_tipo("Anuais", ["Ano"])
        _, grupos, _ = self.grupos()
        self.assertEqual(grupos[chave].documentos, [])

    def test_vence_o_tipo_com_mais_indices_preenchidos(self):
        self.perfil_com_tipo("Serviços", ["Objeto"])
        contratos = self.perfil_com_tipo("Contratos", ["Objeto", "Contratado"])
        _, grupos, _ = self.grupos()
        self.assertEqual(len(grupos[contratos].documentos), 2)
        self.assertEqual(grupos["servicos"].documentos, [])

    def test_empate_fica_com_o_primeiro_do_perfil(self):
        primeiro = self.perfil_com_tipo("Serviços", ["Objeto"])
        self.perfil_com_tipo("Objetos", ["Objeto"])
        _, grupos, _ = self.grupos()
        self.assertEqual(len(grupos[primeiro].documentos), 2)

    def test_palavras_chave_pela_pasta(self):
        gerar_pdf(self.pasta / "CONTRATOS_2021" / "x.pdf", 1)
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO, "contrato")
        _, grupos, _ = self.grupos()
        self.assertIn("x.pdf", [d.nome_arquivo for d in grupos[chave].documentos])

    def test_busca_por_indice_do_tipo(self):
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        catalogo, grupos, _ = self.grupos()
        recorte = cat.subcatalogo(catalogo, grupos[chave])
        resultado = busca.buscar(recorte, busca.Criterios(filtros={"Contratado": "acme"}))
        self.assertEqual([d.nome_arquivo for d in resultado.documentos], ["c1.pdf"])
        # Busca livre no índice continua olhando todos os campos, não só os do tipo
        livre = busca.buscar(recorte, busca.Criterios(termo="10", escopo_nome=False))
        self.assertEqual([d.nome_arquivo for d in livre.documentos], ["c1.pdf"])

    def test_agrupamento_da_contagem_usa_o_tipo_criado(self):
        from ged.contagem import OpcoesContagem, agrupar, contar

        self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        resultado = contar(cat.varrer(self.pasta), OpcoesContagem())
        totais = {linha.grupo: linha.arquivos for linha in agrupar(resultado, "tipo")}
        self.assertEqual(totais.get("Contratos"), 2)


class TestLinhaDeComandoTipos(TesteComPasta):
    def test_listar(self):
        codigo, saida, _ = rodar_cli("tipos")
        self.assertEqual(codigo, 0)
        self.assertIn("despesa", saida)
        self.assertIn("os que os documentos trouxerem", saida)

    def test_criar_listar_buscar_e_excluir(self):
        montar_acervo(self.pasta)
        perfil = str(self.pasta / "perfil.json")
        codigo, saida, erro = rodar_cli("tipos", "--perfil", perfil, "criar", "Contratos",
                                        "--indices", "Contratado,Objeto,Vigência", "--palavras", "contrato")
        self.assertEqual(codigo, 0, erro)
        self.assertIn('Tipo "Contratos" criado (chave: contratos)', saida)

        codigo, saida, _ = rodar_cli("tipos", "--perfil", perfil)
        self.assertIn("Contratado, Objeto, Vigência", saida)
        self.assertIn("palavras-chave: contrato", saida)

        codigo, saida, erro = rodar_cli("buscar", str(self.pasta), "--perfil", perfil, "--tipo", "contratos",
                                        "--filtro", "Contratado=beta")
        self.assertEqual(codigo, 0, erro)
        self.assertIn("Tipo selecionado: Contratos", saida)
        self.assertIn("Resultado: 1 documento(s)", saida)

        codigo, saida, _ = rodar_cli("tipos", "--perfil", perfil, "excluir", "Contratos")
        self.assertEqual(codigo, 0)
        self.assertEqual(len(perfis.carregar_arquivo(perfil).tipos), 3)

    def test_criar_sem_perfil_grava_ao_lado_do_programa(self):
        codigo, _, erro = rodar_cli("tipos", "criar", "Contratos", "--indices", "Contratado")
        self.assertEqual(codigo, 0, erro)
        self.assertTrue((self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL).is_file())

    def test_erros_viram_mensagem_e_codigo_2(self):
        codigo, _, erro = rodar_cli("tipos", "criar", "Despesas", "--indices", "A")
        self.assertEqual(codigo, 2)
        self.assertIn("Já existe", erro)
        codigo, _, erro = rodar_cli("tipos", "excluir", "inexistente")
        self.assertEqual(codigo, 2)
        self.assertIn("não encontrado", erro)

    def test_indices_obrigatorios(self):
        codigo, _, _ = rodar_cli("tipos", "criar", "Contratos")
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()

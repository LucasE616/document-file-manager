"""Interface gráfica: a janela de verdade, dirigida pelo próprio teste.

Precisam de uma tela. No Windows e no macOS ela existe; no Linux sem tela
(CI, servidor), rode com o Xvfb:

    xvfb-run -a python main.py testes

Sem Tkinter ou sem tela, estes testes são pulados — os demais rodam.

Os diálogos modais (`wait_window`) travariam o teste, então a pergunta do
tipo de documento é trocada por um dublê que só devolve a escolha atual; os
próprios diálogos são testados abrindo-os diretamente e chamando os métodos
dos botões.
"""
from __future__ import annotations

import gc
import os
import sys
import threading
import time
import traceback
import unittest
from unittest import mock

try:
    import tkinter as tk

    from ged.gui import aba_consulta as modulo_consulta
    from ged.gui import aba_contagem as modulo_contagem
    from ged.gui import app as modulo_app
    from ged.gui import dialogo_novo_tipo as modulo_novo_tipo
    from ged.gui import dialogo_tipo as modulo_tipo
    from ged.gui.dialogo_tipo import Escolha

    _raiz = tk.Tk()
    _raiz.destroy()
    MOTIVO = ""
except Exception as exc:  # sem Tkinter, ou sem tela
    MOTIVO = f"interface gráfica indisponível: {exc}"
    # No CI a interface tem de ser testada: pular em silêncio esconderia
    # que nenhum teste de tela rodou.
    if os.environ.get("GED_EXIGIR_INTERFACE"):
        raise RuntimeError(f"GED_EXIGIR_INTERFACE definido, mas {MOTIVO}") from exc

from ged import catalogo as cat, leitores, perfil as perfis
from tests.base import PDF_OK, TesteComPasta
from tests.test_tipos import INDICES_CONTRATO, montar_acervo

PPM_1X1 = b"P6\n1 1\n255\n\x00\x00\x00"


class _DialogoQueConfirma:
    """Dublê do diálogo de tipo: confirma a escolha atual sem abrir janela."""

    def __init__(self, master, grupos, sem_tipo, contagem, atual):
        self.escolha = atual
        self.perfil_alterado = False


def _coletar_lixo_do_tk():
    """Recolhe o lixo do Tk na thread principal, antes que uma thread de trabalho o faça.

    O coletor de lixo do Python roda na thread que estiver alocando memória.
    Se for uma thread de trabalho e o lixo for uma `StringVar` de uma janela
    já fechada, o tkinter tenta repassar a chamada à thread principal e
    espera 1 s por variável, porque o teste usa `update()` em vez de
    `mainloop()`: no CI, a leitura do diretório parou por 8 s ("o diretório
    não foi lido"). Se o lixo for a própria instância do Tk, o processo aborta
    ("Tcl_AsyncDelete: async handler deleted by the wrong thread").
    No programa isso não acontece: há uma janela só, sempre no `mainloop()`.
    """
    gc.collect()


@unittest.skipIf(MOTIVO, MOTIVO)
class TesteJanela(TesteComPasta):
    def setUp(self):
        super().setUp()
        for alvo in (mock.patch("ged.dependencias.faltando", return_value=[]),
                     mock.patch.object(modulo_consulta, "DialogoTipo", _DialogoQueConfirma)):
            alvo.start()
            self.addCleanup(alvo.stop)
        # Exceção dentro de um callback do Tk abriria uma janela de erro, e a
        # de um __del__ só seria impressa: o teste nem perceberia. Aqui as
        # duas são guardadas e reprovadas no fim.
        self.erros_tk: list[str] = []
        anterior = sys.unraisablehook
        sys.unraisablehook = self._guardar_ignorada
        self.addCleanup(setattr, sys, "unraisablehook", anterior)
        self.addCleanup(self._sem_erros_no_tk)

        _coletar_lixo_do_tk()
        self.app = modulo_app.App()
        self.app.withdraw()
        self.app.wait_window = lambda _janela=None: None
        self.app.report_callback_exception = (
            lambda tipo, valor, rastro: self.erros_tk.append("".join(traceback.format_exception(tipo, valor, rastro)))
        )
        self.addCleanup(self._fechar)

    def _guardar_ignorada(self, ignorada):
        rastro = "".join(traceback.format_exception(ignorada.exc_type, ignorada.exc_value, ignorada.exc_traceback))
        self.erros_tk.append(f"exceção ignorada em {ignorada.object!r}:\n{rastro}")

    def _sem_erros_no_tk(self):
        if self.erros_tk:
            self.fail("exceção na interface (callback do Tk ou __del__):\n" + "\n".join(self.erros_tk))

    def _fechar(self, atributo="app"):
        """Fecha a janela guardada em `self.<atributo>` e recolhe o lixo dela na thread principal."""
        app = getattr(self, atributo)
        setattr(self, atributo, None)
        app._cancelar.set()
        try:
            # Direto no Tcl: o after_cancel do tkinter quebra (TypeError) com
            # os `after` que o próprio Tk agenda em algumas versões.
            for ident in app.tk.splitlist(app.tk.call("after", "info")):
                try:
                    app.tk.call("after", "cancel", ident)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        finally:
            try:
                app.destroy()
            except tk.TclError:
                pass
            del app
            _coletar_lixo_do_tk()

    def esperar(self, condicao, limite=8.0, mensagem="a condição não aconteceu a tempo"):
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            self.app.update()
            if condicao():
                return
            time.sleep(0.01)
        self.fail(mensagem)

    def bombear(self, segundos):
        """Deixa a interface rodar por um tempo, processando os `after` agendados."""
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            self.app.update()
            time.sleep(0.01)

    def ler_acervo(self):
        _coletar_lixo_do_tk()
        montar_acervo(self.pasta)
        self.app.var_diretorio.set(str(self.pasta))
        self.app.ler_diretorio()
        self.esperar(lambda: self.app.consulta.catalogo is not None, mensagem="o diretório não foi lido")
        self.esperar(lambda: not (self.app._trabalho and self.app._trabalho.is_alive()))
        self.app.update()

    def linhas_da_tabela(self):
        return len(self.app.consulta.tabela.arvore.get_children())

    def colunas_da_tabela(self):
        return list(self.app.consulta.tabela.arvore["columns"])

    def tarefas_agendadas(self, nome):
        """Quantos `after` pendentes chamam um método com este nome."""
        tk_ = self.app.tk
        return sum(1 for ident in tk_.splitlist(tk_.call("after", "info"))
                   if nome in str(tk_.call("after", "info", ident)))


class TestJanelaPrincipal(TesteJanela):
    def test_le_o_diretorio_e_lista_os_documentos(self):
        self.ler_acervo()
        self.assertEqual(self.app.catalogo_completo.total_documentos, 4)
        self.assertGreater(self.linhas_da_tabela(), 0)
        self.assertEqual(str(self.app.botao_ler["state"]), "normal")

    def test_tipo_criado_vira_colunas_e_campos_de_busca(self):
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        self.ler_acervo()
        consulta = self.app.consulta
        consulta._aplicar_escolha(Escolha(chave=chave))
        self.assertEqual(self.colunas_da_tabela()[:3], INDICES_CONTRATO)
        self.assertEqual(list(consulta._filtros), INDICES_CONTRATO)
        self.assertEqual(self.linhas_da_tabela(), 2)
        self.assertEqual(consulta.botao_tipo["text"], "Tipo: Contratos")

        consulta._filtros["Contratado"].set("acme")
        consulta.buscar()
        self.assertEqual(self.linhas_da_tabela(), 1)

    def test_escolha_de_tipo_que_deixou_de_existir_cai_em_outro(self):
        self.ler_acervo()
        self.app.consulta._aplicar_escolha(Escolha(chave="nao_existe"))
        self.assertEqual(self.app.consulta.escolha.chave, cat.TIPO_OUTRO)


    def test_exporta_o_resultado_da_consulta(self):
        self.ler_acervo()
        for extensao in (".txt", ".csv", ".xlsx"):
            destino = self.pasta / f"busca{extensao}"
            with self.subTest(extensao), \
                 mock.patch.object(modulo_consulta.filedialog, "asksaveasfilename", return_value=str(destino)), \
                 mock.patch.object(modulo_consulta.messagebox, "askyesno", return_value=False):
                self.app.consulta._exportar(extensao)
                self.assertGreater(destino.stat().st_size, 0)


@unittest.skipUnless(PDF_OK, "pypdfium2 não instalado")
class TestAbaContagem(TesteJanela):
    def contar(self):
        contagem = self.app.contagem
        contagem.resultado = None
        _coletar_lixo_do_tk()
        contagem.contar()
        self.esperar(lambda: contagem.resultado is not None, mensagem="a contagem não terminou")
        return contagem.resultado

    def test_conta_agrupa_e_mostra_as_tabelas(self):
        self.ler_acervo()
        resultado = self.contar()
        self.assertEqual((resultado.total_arquivos, resultado.total_paginas), (4, 4))
        contagem = self.app.contagem
        self.assertGreater(len(contagem.tabela_arquivos.arvore.get_children()), 0)
        for rotulo in modulo_contagem.AGRUPAMENTOS.values():
            with self.subTest(rotulo):
                contagem.var_agrupamento.set(rotulo)
                contagem._preencher_totais()
                self.assertGreater(len(contagem.tabela_totais.arvore.get_children()), 0)

    def test_contar_sem_ter_lido_o_diretorio_le_antes(self):
        montar_acervo(self.pasta)
        self.app.var_diretorio.set(str(self.pasta))
        resultado = self.contar()
        self.assertEqual(resultado.total_arquivos, 4)

    def test_periodo_invalido_avisa_e_nao_conta(self):
        self.ler_acervo()
        self.app.contagem.var_de.set("ontem")
        with mock.patch.object(modulo_contagem.messagebox, "showerror") as erro:
            self.app.contagem.contar()
        erro.assert_called_once()
        self.assertIsNone(self.app._trabalho if self.app._trabalho and self.app._trabalho.is_alive() else None)

    def test_exporta_o_resultado_da_contagem(self):
        self.ler_acervo()
        self.contar()
        for extensao in (".txt", ".csv", ".xlsx"):
            destino = self.pasta / f"contagem{extensao}"
            with self.subTest(extensao), \
                 mock.patch.object(modulo_contagem.filedialog, "asksaveasfilename", return_value=str(destino)), \
                 mock.patch.object(modulo_contagem.messagebox, "askyesno", return_value=False):
                self.app.contagem._exportar(extensao)
                self.assertGreater(destino.stat().st_size, 0)


class TestDialogoNovoTipo(TesteJanela):
    def abrir(self, contagem=None, iniciais=None):
        contagem = {"Contratado": 2, "Objeto": 3, "Vazio": 0} if contagem is None else contagem
        dialogo = modulo_novo_tipo.DialogoNovoTipo(self.app, contagem, iniciais)
        self.addCleanup(lambda: dialogo.winfo_exists() and dialogo.destroy())
        return dialogo

    def test_cria_grava_e_ativa_o_tipo(self):
        dialogo = self.abrir(iniciais=["Objeto"])
        self.assertNotIn("Vazio", dialogo._marcas)  # índice sem nenhum documento não é oferecido
        dialogo.var_nome.set("Contratos")
        dialogo._marcas["Contratado"].set(True)
        dialogo.var_outros.set("Fiscal, Gestor")
        dialogo.var_palavras.set("contrato")
        dialogo.criar()

        self.assertEqual(dialogo.chave_criada, "contratos")
        self.assertFalse(dialogo.winfo_exists())
        tipo = perfis.ativo().tipo("contratos")
        self.assertEqual(tipo.indices, ["Contratado", "Objeto", "Fiscal", "Gestor"])
        self.assertEqual(tipo.palavras, ["contrato"])
        self.assertTrue((self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL).is_file())

    def test_dados_invalidos_avisam_e_o_dialogo_continua_aberto(self):
        dialogo = self.abrir()
        with mock.patch.object(modulo_novo_tipo.messagebox, "showwarning") as aviso:
            dialogo.criar()  # sem nome
            dialogo.var_nome.set("Contratos")
            dialogo.criar()  # sem índice
        self.assertEqual(aviso.call_count, 2)
        self.assertIsNone(dialogo.chave_criada)
        self.assertTrue(dialogo.winfo_exists())
        self.assertIsNone(perfis.ativo().tipo("contratos"))

    def test_pasta_sem_indices_permite_digitar_os_indices(self):
        dialogo = self.abrir(contagem={})
        dialogo.var_nome.set("Processos")
        dialogo.var_outros.set("Número do processo, Interessado")
        dialogo.criar()
        self.assertEqual(perfis.ativo().tipo("processos").indices, ["Número do processo", "Interessado"])


class TestDialogoTipo(TesteJanela):
    def abrir(self):
        self.ler_acervo()
        consulta = self.app.consulta
        dialogo = modulo_tipo.DialogoTipo(self.app, consulta.grupos, consulta.sem_tipo,
                                          consulta.contagem_indices, Escolha(chave=cat.TIPO_OUTRO))
        self.addCleanup(lambda: dialogo.winfo_exists() and dialogo.destroy())
        dialogo.wait_window = lambda _janela=None: None
        return dialogo

    def test_botao_criar_parte_dos_indices_marcados_em_outro(self):
        dialogo = self.abrir()
        dialogo._marcas["Contratado"].set(True)
        recebidos = {}

        class Cadastro:
            def __init__(self, master, contagem, iniciais):
                recebidos.update(contagem=contagem, iniciais=iniciais)
                self.chave_criada = "contratos"

        with mock.patch.object(modulo_tipo, "DialogoNovoTipo", Cadastro):
            dialogo.criar_tipo()
        self.assertEqual(recebidos["iniciais"], ["Contratado"])
        self.assertIn("Objeto", recebidos["contagem"])
        self.assertEqual(dialogo.escolha, Escolha(chave="contratos"))
        self.assertTrue(dialogo.perfil_alterado)

    def test_cadastro_cancelado_nao_muda_nada(self):
        dialogo = self.abrir()

        class Cancelado:
            def __init__(self, *args):
                self.chave_criada = None

        with mock.patch.object(modulo_tipo, "DialogoNovoTipo", Cancelado):
            dialogo.criar_tipo()
        self.assertIsNone(dialogo.escolha)
        self.assertFalse(dialogo.perfil_alterado)
        self.assertTrue(dialogo.winfo_exists())

    def test_excluir_tipo_criado(self):
        chave = self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        dialogo = self.abrir()
        grupo = next(g for g in self.app.consulta.grupos if g.chave == chave)
        with mock.patch.object(modulo_tipo.messagebox, "askyesno", return_value=True):
            dialogo._excluir(grupo)
        self.assertTrue(dialogo.perfil_alterado)
        self.assertIsNone(perfis.ativo().tipo(chave))
        self.assertIsNone(perfis.carregar_arquivo(self.pasta_programa / perfis.NOME_ARQUIVO_PERFIL).tipo(chave))

        self.app.consulta.tipos_alterados()
        self.assertNotIn(chave, [g.chave for g in self.app.consulta.grupos])

    def test_tipo_criado_aparece_com_botao_excluir_e_os_padrao_nao(self):
        self.perfil_com_tipo("Contratos", INDICES_CONTRATO)
        dialogo = self.abrir()
        botoes = []

        def coletar(widget):
            for filho in widget.winfo_children():
                if isinstance(filho, tk.ttk.Button) and filho["text"] == "Excluir":
                    botoes.append(filho)
                coletar(filho)

        coletar(dialogo)
        self.assertEqual(len(botoes), 1)


class TestRegressaoInterface(TesteJanela):
    def test_miniatura_nao_deixa_laco_de_espera_para_tras(self):
        """Correção: trocar de seleção antes de a miniatura chegar deixava um laço eterno.

        Cada seleção abria seu próprio laço de espera (25 consultas por
        segundo à fila). Com PDF grande ou em rede, um laço consumia o
        resultado e o outro ficava rodando até fechar o programa — e o uso
        de CPU crescia a cada troca rápida de seleção.
        """
        self.ler_acervo()
        consulta = self.app.consulta
        a, b = [d for d in self.app.catalogo_completo.documentos if d.localizado][:2]
        liberar = threading.Event()

        def miniatura_lenta(caminho, largura):
            liberar.wait(5)
            return PPM_1X1

        with mock.patch.object(leitores, "miniatura_ppm", miniatura_lenta), \
             mock.patch.object(leitores, "imagem_disponivel", return_value=True):
            for documento in (a, b):
                with mock.patch.object(consulta.tabela, "selecionado", return_value=documento):
                    consulta._mostrar_previa()
            liberar.set()
            self.esperar(lambda: consulta.rotulo_previa["text"] != "Carregando...")
            self.bombear(0.3)
        self.assertEqual(self.tarefas_agendadas("_receber_previa"), 0)
        self.assertIsNone(consulta._laco_previa)

    def test_documento_sem_arquivo_encerra_a_espera_da_miniatura(self):
        self.ler_acervo()
        consulta = self.app.consulta
        com_arquivo = next(d for d in self.app.catalogo_completo.documentos if d.localizado)
        sem_arquivo = cat.Documento(nome_arquivo="sumiu.pdf")
        liberar = threading.Event()
        with mock.patch.object(leitores, "miniatura_ppm", lambda c, l: liberar.wait(5) and PPM_1X1), \
             mock.patch.object(leitores, "imagem_disponivel", return_value=True):
            with mock.patch.object(consulta.tabela, "selecionado", return_value=com_arquivo):
                consulta._mostrar_previa()
            with mock.patch.object(consulta.tabela, "selecionado", return_value=sem_arquivo):
                consulta._mostrar_previa()
            liberar.set()
            self.bombear(0.3)
        self.assertEqual(self.tarefas_agendadas("_receber_previa"), 0)
        self.assertEqual(consulta.rotulo_previa["text"], "(sem arquivo para pré-visualizar)")

    def test_tarefa_interrompida_nao_libera_a_interface_da_seguinte(self):
        """Correção: com uma fila só, o fim da tarefa interrompida reativava "Ler diretório".

        A contagem de páginas em segundo plano é interrompida quando o
        usuário pede outra coisa. O laço que esvaziava a fila dela lia o
        próprio "fim" e encerrava a interface — botão "Ler diretório"
        ativo e barra de progresso zerada — com a tarefa nova ainda rodando.
        """
        liberar = threading.Event()
        concluidas = []

        def secundaria(progresso, cancelado):
            while not cancelado():
                time.sleep(0.01)
            return "secundária"

        def principal(progresso, cancelado):
            liberar.wait(5)
            return "principal"

        # Fila esvaziada a cada 1 s: a tarefa interrompida termina e a nova
        # começa antes de alguém ler o "fim" dela — o cenário do defeito,
        # que no uso real dependia da sorte.
        with mock.patch.object(modulo_app, "INTERVALO_FILA_MS", 1000):
            self.app.executar("contando em segundo plano", secundaria, concluidas.append, secundario=True)
            self.bombear(0.05)
            self.app.executar("tarefa principal", principal, concluidas.append)
            self.esperar(lambda: self.app.var_status.get() == "tarefa principal")
            self.bombear(1.3)
            self.assertEqual(str(self.app.botao_ler["state"]), "disabled")
            self.assertEqual(str(self.app.botao_cancelar["state"]), "normal")

            liberar.set()
            self.esperar(lambda: "principal" in concluidas)
        # A interrompida foi substituída: o resultado dela não é entregue
        self.assertEqual(concluidas, ["principal"])
        self.assertEqual(str(self.app.botao_ler["state"]), "normal")

    def test_janela_fechada_nao_deixa_lixo_do_tk_para_as_threads(self):
        """Correção: o lixo de uma janela fechada, coletado numa thread de trabalho, travava a leitura.

        No CI, a StringVar de uma janela de teste já fechada era destruída
        pela thread que lia o diretório; o tkinter esperava 1 s por variável
        pela thread principal, a leitura estourava o tempo e o teste falhava
        com "o diretório não foi lido". Fechar a janela tem de recolher esse
        lixo na thread principal.
        """
        self.outra = modulo_app.App()
        self.outra.withdraw()
        self.outra.var_diretorio.set(str(self.pasta))  # janela usada, com variáveis preenchidas
        self._fechar("outra")

        gc.disable()  # a coleta tem de acontecer só onde o teste mandar
        try:
            terminou = threading.Event()
            inicio = time.monotonic()
            threading.Thread(target=lambda: (gc.collect(), terminou.set()), daemon=True).start()
            self.esperar(terminou.is_set, limite=5)
        finally:
            gc.enable()
        self.assertLess(time.monotonic() - inicio, 0.9, "a coleta na thread de trabalho ficou esperando o Tk")
        self.assertEqual(self.erros_tk, [])

    def test_erro_na_tarefa_aparece_e_libera_a_interface(self):
        def quebra(progresso, cancelado):
            raise RuntimeError("falha de teste")

        with mock.patch.object(modulo_app, "janela_de_erro") as janela:
            self.app.executar("vai falhar", quebra, lambda _r: None)
            self.esperar(lambda: janela.called)
        self.assertIn("falha de teste", janela.call_args[0][2])
        self.assertEqual(self.app.var_status.get(), "A operação falhou.")
        self.assertEqual(str(self.app.botao_ler["state"]), "normal")


if __name__ == "__main__":
    unittest.main()

"""Janela principal: diretório, tarefas em segundo plano e as duas abas.

As duas abas trabalham sobre o mesmo catálogo — o diretório é lido uma vez
só e serve à consulta e à contagem.

Toda tarefa demorada roda numa thread e conversa com a interface por uma
fila, que a thread principal esvazia periodicamente. A thread de trabalho
nunca toca no Tk: o contador antigo chamava `root.after` de dentro da
thread a cada arquivo, o que o Tkinter não garante ser seguro e, em pastas
grandes, inundava a fila de eventos até a janela travar.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .. import NOME, __version__, catalogo as cat, conteudo as cont, dependencias, leitores
from ..texto import formatar_inteiro
from .widgets import COR_SUAVE, janela_de_erro

INTERVALO_FILA_MS = 100
INTERVALO_PROGRESSO_S = 0.1

Trabalho = Callable[[Callable[[cat.Progresso], None], Callable[[], bool]], Any]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{NOME} — consulta, contagem e auditoria do acervo digitalizado")
        self._dimensionar_para_a_tela()
        self.report_callback_exception = self._erro_inesperado

        self.catalogo_completo: cat.Catalogo | None = None
        self.cache = cont.CacheConteudo()

        self._fila: queue.Queue = queue.Queue()
        self._trabalho: threading.Thread | None = None
        self._trabalho_secundario = False
        self._cancelar = threading.Event()
        self._ultimo_progresso = 0.0

        self._montar()
        self.after(200, self._verificar_dependencias)

    def _dimensionar_para_a_tela(self) -> None:
        """Abre numa janela que cabe na tela, inclusive em notebook."""
        largura = min(1280, self.winfo_screenwidth() - 60)
        altura = min(760, self.winfo_screenheight() - 110)
        x = max((self.winfo_screenwidth() - largura) // 2, 0)
        y = max((self.winfo_screenheight() - altura) // 3, 0)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self.minsize(900, 540)

    # ------------------------------------------------------------ montagem
    def _montar(self) -> None:
        from .aba_consulta import AbaConsulta
        from .aba_contagem import AbaContagem

        topo = ttk.Frame(self, padding=(8, 6, 8, 2))
        topo.pack(fill="x")
        ttk.Label(topo, text="Diretório:").grid(row=0, column=0, sticky="w")
        self.var_diretorio = tk.StringVar()
        entrada = ttk.Entry(topo, textvariable=self.var_diretorio)
        entrada.grid(row=0, column=1, sticky="we", padx=5)
        entrada.bind("<Return>", lambda _e: self.ler_diretorio())
        topo.columnconfigure(1, weight=1)
        ttk.Button(topo, text="Escolher...", command=self._escolher_diretorio).grid(row=0, column=2)
        self.var_subpastas = tk.BooleanVar(value=True)
        ttk.Checkbutton(topo, text="Subpastas", variable=self.var_subpastas).grid(row=0, column=3, padx=(8, 4))
        self.botao_ler = ttk.Button(topo, text="Ler diretório", command=self.ler_diretorio)
        self.botao_ler.grid(row=0, column=4, padx=2)
        self.botao_cancelar = ttk.Button(topo, text="Cancelar", command=self.cancelar, state="disabled")
        self.botao_cancelar.grid(row=0, column=5, padx=2)

        linha_status = ttk.Frame(self, padding=(8, 0))
        linha_status.pack(fill="x")
        self.progresso = ttk.Progressbar(linha_status, mode="determinate", length=170)
        self.progresso.pack(side="left")
        self.var_status = tk.StringVar(value="Escolha um diretório para começar.")
        ttk.Label(linha_status, textvariable=self.var_status, foreground=COR_SUAVE).pack(side="left", padx=8)

        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=8, pady=(4, 6))
        self.consulta = AbaConsulta(self.abas, self)
        self.contagem = AbaContagem(self.abas, self)
        self.abas.add(self.consulta, text="  Consulta  ")
        self.abas.add(self.contagem, text="  Contagem e auditoria  ")
        self.abas.bind("<<NotebookTabChanged>>", lambda _e: self._ao_trocar_aba())

    def aba_consulta_ativa(self) -> bool:
        return self.abas.select() == str(self.consulta)

    def _ao_trocar_aba(self) -> None:
        if self.aba_consulta_ativa():
            self.consulta.ao_mostrar()

    def definir_status(self, texto: str) -> None:
        self.var_status.set(texto)

    # --------------------------------------------------------- diretório
    def _escolher_diretorio(self) -> None:
        escolhido = filedialog.askdirectory(title="Escolha o diretório do acervo")
        if escolhido:
            self.var_diretorio.set(str(Path(escolhido)))
            self.ler_diretorio()

    def ler_diretorio(self, depois: Callable[[], None] | None = None) -> None:
        raiz = self.var_diretorio.get().strip().strip('"')
        if not raiz:
            messagebox.showwarning(NOME, "Escolha um diretório primeiro.")
            return
        if not Path(raiz).is_dir():
            messagebox.showerror(NOME, f"Diretório não encontrado:\n{raiz}")
            return
        incluir = self.var_subpastas.get()

        def trabalho(progresso, cancelado):
            return cat.varrer(raiz, incluir_subpastas=incluir, progresso=progresso, cancelado=cancelado)

        def concluir(catalogo: cat.Catalogo) -> None:
            if catalogo.cancelado:
                self.definir_status("Leitura do diretório cancelada.")
                return
            self.catalogo_completo = catalogo
            self.cache = cont.CacheConteudo()
            self.definir_status(
                f"{formatar_inteiro(catalogo.total_documentos)} documento(s), "
                f"{formatar_inteiro(catalogo.arquivos_encontrados)} arquivo(s), "
                f"{formatar_inteiro(catalogo.xmls_lidos)} índice(s) XML."
            )
            self.contagem.novo_catalogo(catalogo)
            self.consulta.novo_catalogo(catalogo)
            if depois:
                depois()
            else:
                self._contar_paginas_faltantes()

        self.executar("Lendo o diretório...", trabalho, concluir)

    def _contar_paginas_faltantes(self) -> None:
        """Conta, em segundo plano, as páginas dos arquivos que nenhum índice informa."""
        catalogo = self.catalogo_completo
        if catalogo is None:
            return
        faltantes = [d for d in catalogo.documentos if d.localizado and d.paginas is None and not d.lido
                     and leitores.disponivel(d.extensao)]
        if not faltantes:
            return
        from ..contagem import ler_paginas_faltantes

        def concluir(lidos: int) -> None:
            self.consulta.atualizar_totais()
            self.definir_status(f"Páginas contadas em {formatar_inteiro(lidos)} arquivo(s) sem índice.")

        self.executar(
            f"Contando páginas de {formatar_inteiro(len(faltantes))} arquivo(s) sem índice...",
            lambda p, c: ler_paginas_faltantes(catalogo, p, c),
            concluir,
            secundario=True,
        )

    # ------------------------------------------------------------ tarefas
    def ocupado(self, avisar: bool = True) -> bool:
        if self._trabalho and self._trabalho.is_alive():
            if avisar:
                messagebox.showinfo(NOME, "Aguarde a operação em andamento terminar, ou clique em Cancelar.")
            return True
        return False

    def executar(self, status: str, trabalho: Trabalho, ao_concluir: Callable[[Any], None],
                 secundario: bool = False) -> bool:
        """Roda `trabalho(progresso, cancelado)` numa thread e entrega o resultado a `ao_concluir`.

        Uma tarefa secundária (a contagem de páginas logo após a leitura) é
        interrompida automaticamente quando o usuário pede outra coisa.
        """
        if self._trabalho and self._trabalho.is_alive():
            if self._trabalho_secundario and not secundario:
                self._cancelar.set()
                self.after(150, lambda: self.executar(status, trabalho, ao_concluir, secundario))
                return True
            self.ocupado(avisar=True)
            return False

        self._cancelar.clear()
        self._trabalho_secundario = secundario
        self.botao_ler.configure(state="disabled")
        self.botao_cancelar.configure(state="normal")
        self.progresso.configure(mode="indeterminate")
        self.progresso.start(12)
        self.definir_status(status)
        self._ultimo_progresso = 0.0

        def alvo() -> None:
            try:
                resultado = trabalho(self._progresso_da_thread, self._cancelar.is_set)
            except Exception:
                self._fila.put(("erro", traceback.format_exc()))
                return
            self._fila.put(("fim", ao_concluir, resultado))

        self._trabalho = threading.Thread(target=alvo, daemon=True)
        self._trabalho.start()
        self.after(INTERVALO_FILA_MS, self._drenar_fila)
        return True

    def _progresso_da_thread(self, progresso: cat.Progresso) -> None:
        """Chamado pela thread: só enfileira, e no máximo dez vezes por segundo."""
        agora = time.monotonic()
        if agora - self._ultimo_progresso >= INTERVALO_PROGRESSO_S or progresso.atual >= progresso.total > 0:
            self._ultimo_progresso = agora
            self._fila.put(("progresso", progresso))

    def cancelar(self) -> None:
        self._cancelar.set()
        self.definir_status("Cancelando...")

    def _terminar(self) -> None:
        self.progresso.stop()
        self.progresso.configure(mode="determinate", value=0)
        self.botao_ler.configure(state="normal")
        self.botao_cancelar.configure(state="disabled")

    def _drenar_fila(self) -> None:
        ultimo: cat.Progresso | None = None
        try:
            while True:
                item = self._fila.get_nowait()
                tipo = item[0]
                if tipo == "progresso":
                    ultimo = item[1]
                elif tipo == "erro":
                    self._terminar()
                    self.definir_status("A operação falhou.")
                    janela_de_erro(self, "Erro", item[1])
                    return
                elif tipo == "fim":
                    self._terminar()
                    item[1](item[2])
                    return
        except queue.Empty:
            pass
        if ultimo is not None:
            if ultimo.total:
                self.progresso.stop()
                self.progresso.configure(mode="determinate", maximum=ultimo.total, value=ultimo.atual)
                contador = f"{formatar_inteiro(ultimo.atual)}/{formatar_inteiro(ultimo.total)}  "
            else:
                contador = ""
            self.definir_status(f"[{ultimo.fase}] {contador}{ultimo.mensagem}")
        if self._trabalho and self._trabalho.is_alive() or not self._fila.empty():
            self.after(INTERVALO_FILA_MS, self._drenar_fila)
        else:
            self._terminar()

    # ------------------------------------------------------------- erros
    def _erro_inesperado(self, tipo, valor, rastro) -> None:
        janela_de_erro(self, "Erro inesperado", "".join(traceback.format_exception(tipo, valor, rastro)))

    # ------------------------------------------------------- dependências
    def _verificar_dependencias(self) -> None:
        """Na primeira execução como script, instala sozinho o que faltar.

        No executável tudo já vem embutido e esta etapa não faz nada.
        """
        faltando = dependencias.faltando()
        if not faltando:
            return
        janela = tk.Toplevel(self)
        janela.title(f"{NOME} — preparando")
        janela.transient(self)
        janela.resizable(False, False)
        corpo = ttk.Frame(janela, padding=16)
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, text="Preparando o programa (só na primeira vez)", font=("", 11, "bold")).pack(anchor="w")
        nomes = ", ".join(p.pip for p in faltando)
        var = tk.StringVar(value=f"Instalando componentes gratuitos: {nomes}...")
        ttk.Label(corpo, textvariable=var, wraplength=420).pack(anchor="w", pady=(4, 8))
        barra = ttk.Progressbar(corpo, mode="indeterminate", length=420)
        barra.pack(fill="x")
        barra.start(12)
        janela.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - janela.winfo_width()) // 2
        janela.geometry(f"+{max(x, 0)}+{self.winfo_rooty() + 80}")
        fila: queue.Queue = queue.Queue()

        threading.Thread(
            target=lambda: fila.put(dependencias.instalar(faltando, aviso=lambda t: fila.put(("aviso", t)))),
            daemon=True,
        ).start()

        def acompanhar() -> None:
            try:
                while True:
                    item = fila.get_nowait()
                    if isinstance(item, tuple) and item and item[0] == "aviso":
                        var.set(item[1])
                        continue
                    barra.stop()
                    janela.destroy()
                    leitores.recarregar()
                    self.consulta.dependencias_atualizadas()
                    if item:
                        messagebox.showwarning(NOME, dependencias.mensagem_de_falha(item))
                    return
            except queue.Empty:
                self.after(200, acompanhar)

        self.after(200, acompanhar)


def executar() -> None:
    app = App()
    app.mainloop()


def versao() -> str:
    return f"{NOME} {__version__}"

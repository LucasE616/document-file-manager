"""Cria um tipo documental: nome, índices e, se quiser, palavras-chave.

O tipo vai para o perfil do acervo (`ged_perfil.json`) e passa a aparecer
na pergunta "Qual tipo de documento você vai consultar?" desta e das
próximas vezes que o programa abrir — sem mexer no código.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import perfil as perfis
from ..texto import formatar_inteiro
from .widgets import COR_DICA, COR_SUAVE, AreaRolavel


class DialogoNovoTipo(tk.Toplevel):
    """Pergunta nome, índices e palavras-chave e grava o tipo no perfil.

    `contagem` é {índice: em quantos documentos ele está preenchido}, para
    o usuário escolher entre os índices que a pasta tem; `iniciais` já vêm
    marcados (os de "Outro tipo de documento", quando ele parte de lá).
    Depois de fechado, `chave_criada` diz o tipo criado, ou None.
    """

    def __init__(self, master, contagem: dict[str, int], iniciais: list[str] | None = None) -> None:
        super().__init__(master)
        self.title("Criar tipo documental")
        self.resizable(False, False)
        self.chave_criada: str | None = None
        iniciais = iniciais or []

        corpo = ttk.Frame(self, padding=(16, 14))
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="Novo tipo documental", font=("", 11, "bold")).pack(anchor="w")
        ttk.Label(corpo, text="Os índices escolhidos serão os campos de busca e as colunas deste tipo.",
                  foreground=COR_SUAVE).pack(anchor="w", pady=(2, 10))

        ttk.Label(corpo, text="Nome (ex.: Contratos, Portarias de pessoal, Processos)").pack(anchor="w")
        self.var_nome = tk.StringVar(self)
        self.entrada_nome = ttk.Entry(corpo, textvariable=self.var_nome, width=48)
        self.entrada_nome.pack(anchor="w", fill="x", pady=(2, 10))

        ttk.Label(corpo, text="Índices do tipo").pack(anchor="w")
        self._marcas: dict[str, tk.BooleanVar] = {}
        presentes = [campo for campo, quantos in contagem.items() if quantos > 0]
        if presentes:
            area = AreaRolavel(corpo, altura_max=160)
            area.pack(fill="x", pady=(2, 0))
            for i, campo in enumerate(presentes):
                var = tk.BooleanVar(self, value=campo in iniciais)
                self._marcas[campo] = var
                ttk.Checkbutton(area.interno, text=f"{campo} ({formatar_inteiro(contagem[campo])})",
                                variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 18), pady=1)
            area.ajustar_altura()
            ttk.Label(corpo, text="Entre parênteses, em quantos documentos desta pasta o índice está preenchido.",
                      foreground=COR_DICA, font=("", 8)).pack(anchor="w")
        else:
            ttk.Label(corpo, text="Esta pasta não tem índices XML — digite abaixo os índices do tipo.",
                      foreground=COR_DICA, font=("", 8)).pack(anchor="w")

        ttk.Label(corpo, text="Outros índices, que esta pasta não tem (separados por vírgula)").pack(
            anchor="w", pady=(8, 0))
        self.var_outros = tk.StringVar(self)
        ttk.Entry(corpo, textvariable=self.var_outros, width=48).pack(anchor="w", fill="x", pady=(2, 10))

        ttk.Label(corpo, text="Palavras-chave — opcional (separadas por vírgula)").pack(anchor="w")
        self.var_palavras = tk.StringVar(self)
        ttk.Entry(corpo, textvariable=self.var_palavras, width=48).pack(anchor="w", fill="x", pady=(2, 0))
        ttk.Label(corpo,
                  text="Procuradas no nome das pastas e no campo Título do índice para reconhecer\n"
                       "documentos deste tipo. Sem elas, o tipo reconhece os documentos pelos índices.",
                  foreground=COR_DICA, font=("", 8), justify="left").pack(anchor="w")

        destino = perfis.arquivo_para_gravar(perfis.ativo())
        ttk.Label(corpo, text=f"O tipo será gravado em {destino}", foreground=COR_DICA, font=("", 8),
                  wraplength=420, justify="left").pack(anchor="w", pady=(10, 0))

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(14, 0))
        ttk.Button(botoes, text="Criar", command=self.criar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

        self.transient(master)
        self.grab_set()
        self.bind("<Return>", lambda _e: self.criar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.entrada_nome.focus_set()
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 30
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def indices(self) -> list[str]:
        marcados = [campo for campo, var in self._marcas.items() if var.get()]
        outros = [i.strip() for i in self.var_outros.get().split(",") if i.strip()]
        return marcados + outros

    def criar(self) -> None:
        try:
            perfil, chave = perfis.criar_tipo(perfis.ativo(), self.var_nome.get(), self.indices(),
                                              self.var_palavras.get())
            perfil = perfis.salvar(perfil)
        except perfis.ErroPerfil as exc:
            messagebox.showwarning("Criar tipo documental", str(exc), parent=self)
            return
        perfis.definir(perfil)
        self.chave_criada = chave
        self.destroy()

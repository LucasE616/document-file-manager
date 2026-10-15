"""Pergunta qual tipo documental consultar."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk

from .. import catalogo as cat
from ..texto import formatar_inteiro
from .widgets import COR_AVISO, COR_DICA, COR_SUAVE, AreaRolavel


@dataclass
class Escolha:
    """O que o usuário decidiu no diálogo de tipo."""

    chave: str  # chave de um tipo do perfil, ou "outro"
    indices: list[str] = field(default_factory=list)  # só em "outro"


class DialogoTipo(tk.Toplevel):
    """Mostra os tipos do perfil — cada um com quantos documentos dele existem
    na pasta — e a opção "Outro tipo de documento", em que o próprio usuário
    escolhe quais índices quer buscar.
    """

    def __init__(self, master, grupos: list[cat.GrupoTipo], sem_tipo: int,
                 contagem: dict[str, int], atual: Escolha) -> None:
        super().__init__(master)
        self.title("Tipo de documento")
        self.resizable(False, False)
        self.escolha: Escolha | None = None

        corpo = ttk.Frame(self, padding=(16, 14))
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="Qual tipo de documento você vai consultar?", font=("", 11, "bold")).pack(anchor="w")
        ttk.Label(corpo, text="Os campos de busca e as colunas da tabela serão os índices do tipo escolhido.",
                  foreground=COR_SUAVE).pack(anchor="w", pady=(2, 12))

        self.var_tipo = tk.StringVar(value=atual.chave)

        for grupo in grupos:
            vazio = grupo.total_documentos == 0
            if vazio:
                detalhe = "nenhum documento deste tipo nesta pasta"
            else:
                detalhe = (f"{formatar_inteiro(grupo.total_documentos)} documento(s) · "
                           f"{formatar_inteiro(grupo.total_paginas)} página(s)")
            ttk.Radiobutton(corpo, text=f"{grupo.rotulo}   —   {detalhe}", value=grupo.chave,
                            variable=self.var_tipo, command=self._ao_trocar,
                            state="disabled" if vazio else "normal").pack(anchor="w", pady=(2, 0))
            if not vazio:
                indices = ", ".join(grupo.vocabulario[:7]) + ("..." if len(grupo.vocabulario) > 7 else "")
                ttk.Label(corpo, text=f"        índices: {indices or '(nenhum)'}", foreground=COR_DICA,
                          font=("", 8)).pack(anchor="w")

        ttk.Separator(corpo).pack(fill="x", pady=10)

        ttk.Radiobutton(corpo, text=f"{cat.ROTULO_OUTRO}   —   escolher os índices", value=cat.TIPO_OUTRO,
                        variable=self.var_tipo, command=self._ao_trocar).pack(anchor="w")
        if sem_tipo:
            ttk.Label(corpo, text=f"        {formatar_inteiro(sem_tipo)} documento(s) desta pasta não se "
                                  "encaixam nos tipos acima", foreground=COR_AVISO, font=("", 8)).pack(anchor="w")

        self.quadro_indices = ttk.Frame(corpo, padding=(22, 6, 0, 0))
        self.quadro_indices.pack(fill="x")

        self._marcas: dict[str, tk.BooleanVar] = {}
        self._caixas: list[ttk.Checkbutton] = []
        self._botoes_atalho: list[ttk.Button] = []
        # Índices vazios em todos os documentos ficam de fora: marcá-los
        # não traria documento nenhum.
        uteis = [campo for campo, quantos in contagem.items() if quantos > 0]
        if uteis:
            area = AreaRolavel(self.quadro_indices, altura_max=150)
            area.pack(fill="x")
            for i, campo in enumerate(uteis):
                var = tk.BooleanVar(value=campo in atual.indices)
                self._marcas[campo] = var
                caixa = ttk.Checkbutton(area.interno, text=f"{campo} ({formatar_inteiro(contagem[campo])})",
                                        variable=var)
                caixa.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 18), pady=1)
                self._caixas.append(caixa)
            area.ajustar_altura()

            atalhos = ttk.Frame(self.quadro_indices)
            atalhos.pack(fill="x", pady=(4, 0))
            for texto, valor in (("Marcar todos", True), ("Desmarcar todos", False)):
                botao = ttk.Button(atalhos, text=texto, command=lambda v=valor: self._marcar(v))
                botao.pack(side="left", padx=(0, 6))
                self._botoes_atalho.append(botao)
            ttk.Label(self.quadro_indices,
                      text="Entre parênteses, em quantos documentos o índice está preenchido. Serão listados\n"
                           "os documentos que têm ao menos um dos índices marcados.",
                      foreground=COR_DICA, font=("", 8), justify="left").pack(anchor="w", pady=(4, 0))
        else:
            ttk.Label(self.quadro_indices,
                      text="Nenhum índice XML nesta pasta — todos os documentos serão listados, e a busca\n"
                           "fica por conta do nome do arquivo e do conteúdo do PDF.",
                      foreground=COR_DICA, font=("", 8), justify="left").pack(anchor="w")

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(16, 0))
        ttk.Button(botoes, text="Confirmar", command=self._confirmar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

        self._ao_trocar()
        self.transient(master)
        self.grab_set()
        self.bind("<Return>", lambda _e: self._confirmar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 40
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _ao_trocar(self) -> None:
        """A lista de índices só vale para "outro tipo"; fica apagada nos demais."""
        estado = "normal" if self.var_tipo.get() == cat.TIPO_OUTRO else "disabled"
        for widget in self._caixas + self._botoes_atalho:
            widget.configure(state=estado)

    def _marcar(self, valor: bool) -> None:
        for var in self._marcas.values():
            var.set(valor)

    def _confirmar(self) -> None:
        chave = self.var_tipo.get()
        if chave != cat.TIPO_OUTRO:
            self.escolha = Escolha(chave=chave)
            self.destroy()
            return
        indices = [campo for campo, var in self._marcas.items() if var.get()]
        if self._marcas and not indices:
            messagebox.showwarning("Escolha os índices",
                                   "Marque pelo menos um índice para buscar neste tipo de documento.", parent=self)
            return
        self.escolha = Escolha(chave=cat.TIPO_OUTRO, indices=indices)
        self.destroy()

"""Componentes de interface reaproveitados pelas duas abas."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

COR_SUAVE = "#555555"
COR_DICA = "#777777"
COR_AVISO = "#8F6223"
COR_ERRO = "#9B3A34"


class AreaRolavel(ttk.Frame):
    """Contêiner que cresce até uma altura máxima e depois rola.

    Existe para o bloco de filtros: o número de campos depende do acervo,
    e sem um teto ele empurraria a tabela para fora da tela.
    """

    def __init__(self, master, altura_max: int = 116) -> None:
        super().__init__(master)
        self.altura_max = altura_max
        self.tela = tk.Canvas(self, highlightthickness=0, height=1)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.interno = ttk.Frame(self.tela)
        self._janela = self.tela.create_window((0, 0), window=self.interno, anchor="nw")
        self.tela.configure(yscrollcommand=self.barra.set)
        self.tela.pack(side="left", fill="both", expand=True)
        self.interno.bind("<Configure>", self.ajustar_altura)
        self.tela.bind("<Configure>", self._ajustar_largura)
        self.bind("<Enter>", lambda _e: self._ligar_roda(True))
        self.bind("<Leave>", self._ao_sair)

    def _ao_sair(self, evento) -> None:
        # Passar o mouse para um campo dentro da área também gera <Leave>;
        # só desliga a roda quando o ponteiro saiu de fato.
        dentro = self.winfo_containing(evento.x_root, evento.y_root)
        while dentro is not None:
            if dentro is self:
                return
            dentro = dentro.master
        self._ligar_roda(False)

    def ajustar_altura(self, _evento=None) -> None:
        self.tela.configure(scrollregion=self.tela.bbox("all"))
        desejada = self.interno.winfo_reqheight()
        self.tela.configure(height=min(desejada, self.altura_max))
        if desejada > self.altura_max:
            self.barra.pack(side="right", fill="y")
        else:
            self.barra.pack_forget()

    def _ajustar_largura(self, evento) -> None:
        self.tela.itemconfigure(self._janela, width=evento.width)

    def _ligar_roda(self, ligar: bool) -> None:
        if ligar:
            self.tela.bind_all("<MouseWheel>", self._rolar)
        else:
            self.tela.unbind_all("<MouseWheel>")

    def _rolar(self, evento) -> None:
        if self.interno.winfo_reqheight() > self.altura_max:
            self.tela.yview_scroll(-1 * (evento.delta // 120 or (1 if evento.delta > 0 else -1)), "units")


def _chave_ordenacao(valor: Any) -> tuple:
    """Números (inclusive '1.234') antes, comparados como número; o resto como texto."""
    if isinstance(valor, (int, float)):
        return (0, valor, "")
    texto = str(valor or "").strip()
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})*|-?\d+", texto):
        return (0, int(texto.replace(".", "")), "")
    # dd/mm/aaaa [hh:mm] ordena como data
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})(?: (\d{2}):(\d{2}))?", texto)
    if m:
        d, mes, a, h, mi = m.groups()
        return (1, 0, f"{a}{mes}{d}{h or '00'}{mi or '00'}")
    return (2, 0, texto.casefold())


class Tabela(ttk.Frame):
    """Treeview com rolagem, ordenação por coluna e um objeto por linha.

    Clicar no cabeçalho ordena; clicar de novo inverte. Números e datas
    ordenam como números e datas, não como texto.
    """

    def __init__(self, master, ao_abrir: Callable[[Any], None] | None = None, altura: int = 10) -> None:
        super().__init__(master)
        self.arvore = ttk.Treeview(self, columns=(), show="headings", selectmode="browse", height=altura)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.arvore.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.arvore.xview)
        self.arvore.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.arvore.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.arvore.tag_configure("problema", foreground=COR_ERRO)
        self.arvore.tag_configure("aviso", foreground=COR_AVISO)
        self._colunas: list[str] = []
        self._linhas: list[tuple[tuple, str, Any]] = []
        self._objetos: dict[str, Any] = {}
        self._ordem: tuple[int, bool] | None = None
        if ao_abrir:
            self.arvore.bind("<Double-1>", lambda _e: self._abrir(ao_abrir))
            self.arvore.bind("<Return>", lambda _e: self._abrir(ao_abrir))

    def _abrir(self, ao_abrir) -> None:
        objeto = self.selecionado()
        if objeto is not None:
            ao_abrir(objeto)

    def definir_colunas(self, colunas: list[str], larguras: dict[str, int] | None = None,
                        largura_padrao: int = 120, numericas: set[str] | None = None) -> None:
        self._colunas = list(colunas)
        self._ordem = None
        self.arvore.configure(columns=self._colunas)
        numericas = numericas or set()
        for i, coluna in enumerate(self._colunas):
            self.arvore.heading(coluna, text=coluna, command=lambda i=i: self.ordenar(i))
            self.arvore.column(
                coluna,
                width=(larguras or {}).get(coluna, largura_padrao),
                anchor="e" if coluna in numericas else "w",
                stretch=False,
            )

    def preencher(self, linhas: list[tuple[tuple, str, Any]]) -> None:
        """linhas: (valores, etiqueta, objeto). A etiqueta pode ser '', 'problema' ou 'aviso'."""
        self._linhas = list(linhas)
        if self._ordem is not None:
            coluna, inverso = self._ordem
            self._linhas.sort(key=lambda l: _chave_ordenacao(l[0][coluna]), reverse=inverso)
        self._desenhar()

    def _desenhar(self) -> None:
        self.arvore.delete(*self.arvore.get_children())
        self._objetos.clear()
        for valores, etiqueta, objeto in self._linhas:
            iid = self.arvore.insert("", "end", values=["" if v is None else v for v in valores],
                                     tags=(etiqueta,) if etiqueta else ())
            self._objetos[iid] = objeto

    def ordenar(self, coluna: int) -> None:
        inverso = bool(self._ordem and self._ordem[0] == coluna and not self._ordem[1])
        self._ordem = (coluna, inverso)
        self._linhas.sort(key=lambda l: _chave_ordenacao(l[0][coluna]), reverse=inverso)
        for i, nome in enumerate(self._colunas):
            seta = (" ▼" if inverso else " ▲") if i == coluna else ""
            self.arvore.heading(nome, text=nome + seta)
        self._desenhar()

    def selecionado(self) -> Any:
        selecao = self.arvore.selection()
        return self._objetos.get(selecao[0]) if selecao else None

    def selecionar_linha_em(self, y: int) -> bool:
        linha = self.arvore.identify_row(y)
        if not linha:
            return False
        self.arvore.selection_set(linha)
        return True

    def limpar(self) -> None:
        self.preencher([])


class Cartao(tk.Frame):
    """Um número grande com um rótulo embaixo — o resumo do antigo contador."""

    def __init__(self, master, rotulo: str, cor: str = "#2563eb") -> None:
        super().__init__(master, bg="white", highlightbackground="#e2e8f0", highlightthickness=1)
        self._cor = cor
        self.valor = tk.Label(self, text="—", font=("Segoe UI", 18, "bold"), fg=cor, bg="white")
        self.valor.pack(padx=14, pady=(8, 0))
        tk.Label(self, text=rotulo, font=("Segoe UI", 9), fg="#475569", bg="white").pack(padx=14, pady=(0, 8))

    def definir(self, texto: str, destaque: bool | None = None) -> None:
        cor = self._cor if destaque is None else ("#dc2626" if destaque else "#64748b")
        self.valor.configure(text=texto, fg=cor)


def dica(master, texto: str, **opcoes) -> ttk.Label:
    return ttk.Label(master, text=texto, foreground=COR_DICA, font=("", 8), **opcoes)


def janela_de_erro(master, titulo: str, detalhe: str) -> None:
    """Erro inesperado com o detalhe técnico copiável.

    Pelo .pyw não há console: sem isto, um erro fecharia a ação em silêncio.
    """
    janela = tk.Toplevel(master)
    janela.title(titulo)
    janela.transient(master)
    corpo = ttk.Frame(janela, padding=12)
    corpo.pack(fill="both", expand=True)
    ttk.Label(corpo, text="Ocorreu um erro inesperado. A operação foi interrompida, mas o programa continua aberto.",
              wraplength=520).pack(anchor="w")
    ttk.Label(corpo, text="Se o problema se repetir, copie o detalhe abaixo e envie para o desenvolvedor.",
              foreground=COR_SUAVE, wraplength=520).pack(anchor="w", pady=(2, 8))
    caixa = tk.Text(corpo, height=12, width=80, wrap="none", font=("Consolas", 9))
    caixa.insert("1.0", detalhe)
    caixa.configure(state="disabled")
    caixa.pack(fill="both", expand=True)
    botoes = ttk.Frame(corpo)
    botoes.pack(fill="x", pady=(8, 0))

    def copiar() -> None:
        janela.clipboard_clear()
        janela.clipboard_append(detalhe)

    ttk.Button(botoes, text="Copiar detalhe", command=copiar).pack(side="left")
    ttk.Button(botoes, text="Fechar", command=janela.destroy).pack(side="right")
    janela.bind("<Escape>", lambda _e: janela.destroy())

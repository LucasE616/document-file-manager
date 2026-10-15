"""Aba Contagem e auditoria: o antigo Contador de Páginas, sobre o mesmo catálogo.

Escolhe os tipos de arquivo e, se quiser, um período; conta as páginas de
cada arquivo e mostra os totais agrupados, os problemas encontrados e a
lista completa — tudo exportável em TXT, CSV e XLSX.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import NOME, catalogo as cat, datas, leitores
from ..contagem import AGRUPAMENTOS, SEM_INDICE, OpcoesContagem, ResultadoContagem, agrupar, caminho_relativo, contar
from ..exportar import contagem as exportar_contagem
from ..texto import formatar_bytes, formatar_inteiro
from .sistema import abrir_arquivo, abrir_pasta_do_arquivo
from .widgets import Cartao, Tabela, dica

ROTULOS_BASE = {rotulo: chave for chave, rotulo in cat.BASES_DATA.items()}
ROTULOS_AGRUPAMENTO = {rotulo: chave for chave, rotulo in AGRUPAMENTOS.items()}


class AbaContagem(ttk.Frame):
    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(4, 6, 4, 4))
        self.app = app
        self.resultado: ResultadoContagem | None = None
        self._montar()

    # ------------------------------------------------------------ montagem
    def _montar(self) -> None:
        opcoes = ttk.Frame(self)
        opcoes.pack(fill="x")

        tipos = ttk.LabelFrame(opcoes, text="Tipos de arquivo", padding=(8, 4))
        tipos.pack(side="left", fill="y")
        self.var_extensoes: list[tuple[tuple[str, ...], tk.BooleanVar]] = []
        for i, (rotulo, extensoes) in enumerate(leitores.FORMATOS):
            var = tk.BooleanVar(value=bool(set(extensoes) & leitores.EXTENSOES_PADRAO))
            ttk.Checkbutton(tipos, text=rotulo, variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))
            self.var_extensoes.append((extensoes, var))

        periodo = ttk.LabelFrame(opcoes, text="Período (opcional)", padding=(8, 4))
        periodo.pack(side="left", fill="y", padx=8)
        self.var_de, self.var_ate = tk.StringVar(), tk.StringVar()
        ttk.Label(periodo, text="De").grid(row=0, column=0, sticky="w")
        ttk.Entry(periodo, textvariable=self.var_de, width=11).grid(row=0, column=1, padx=(4, 8))
        ttk.Label(periodo, text="até").grid(row=0, column=2, sticky="w")
        ttk.Entry(periodo, textvariable=self.var_ate, width=11).grid(row=0, column=3, padx=(4, 8))
        self.var_base = tk.StringVar(value=cat.BASES_DATA[cat.BASE_CRIACAO])
        ttk.Combobox(periodo, textvariable=self.var_base, values=list(cat.BASES_DATA.values()), width=20,
                     state="readonly").grid(row=0, column=4)
        dica(periodo, "aceita 2019, 11/2019 ou 29/11/2019 · copiar o acervo muda a data de criação; "
                      "a data interna do PDF não muda").grid(row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))

        acao = ttk.Frame(opcoes)
        acao.pack(side="left", fill="both", expand=True)
        self.var_aprofundada = tk.BooleanVar(value=False)
        ttk.Checkbutton(acao, text="Conferência aprofundada", variable=self.var_aprofundada).pack(anchor="w")
        dica(acao, "SHA-256, PDF/A declarado e integridade das imagens.\nLê cada arquivo por inteiro: mais lento.",
             justify="left").pack(anchor="w")
        self.botao_contar = ttk.Button(acao, text="Contar páginas", command=self.contar)
        self.botao_contar.pack(anchor="w", pady=(6, 0))

        cartoes = tk.Frame(self)
        cartoes.pack(fill="x", pady=(8, 6))
        self.cartao_arquivos = Cartao(cartoes, "Arquivos", "#2563eb")
        self.cartao_paginas = Cartao(cartoes, "Páginas", "#16a34a")
        self.cartao_erros = Cartao(cartoes, "Com erro", "#dc2626")
        self.cartao_problemas = Cartao(cartoes, "Problemas na auditoria", "#b45309")
        self.cartao_tamanho = Cartao(cartoes, "Tamanho", "#475569")
        for i, cartao in enumerate((self.cartao_arquivos, self.cartao_paginas, self.cartao_erros,
                                    self.cartao_problemas, self.cartao_tamanho)):
            cartoes.columnconfigure(i, weight=1)
            cartao.grid(row=0, column=i, padx=4, sticky="nsew")

        self.detalhes = ttk.Notebook(self)
        self.detalhes.pack(fill="both", expand=True)

        aba_totais = ttk.Frame(self.detalhes, padding=4)
        linha = ttk.Frame(aba_totais)
        linha.pack(fill="x", pady=(0, 4))
        ttk.Label(linha, text="Agrupar por:").pack(side="left")
        self.var_agrupamento = tk.StringVar(value=AGRUPAMENTOS["extensao"])
        caixa = ttk.Combobox(linha, textvariable=self.var_agrupamento, values=list(AGRUPAMENTOS.values()),
                             state="readonly", width=20)
        caixa.pack(side="left", padx=6)
        caixa.bind("<<ComboboxSelected>>", lambda _e: self._preencher_totais())
        self.tabela_totais = Tabela(aba_totais)
        self.tabela_totais.pack(fill="both", expand=True)
        self.detalhes.add(aba_totais, text="Totais")

        aba_problemas = ttk.Frame(self.detalhes, padding=4)
        self.var_info_problemas = tk.StringVar()
        ttk.Label(aba_problemas, textvariable=self.var_info_problemas, font=("", 8)).pack(anchor="w", pady=(0, 4))
        self.tabela_problemas = Tabela(aba_problemas, ao_abrir=self._abrir_problema)
        self.tabela_problemas.definir_colunas(["Categoria", "Arquivo", "Detalhe", "Caminho"],
                                              {"Categoria": 260, "Arquivo": 240, "Detalhe": 340, "Caminho": 420})
        self.tabela_problemas.pack(fill="both", expand=True)
        self.detalhes.add(aba_problemas, text="Problemas")

        aba_arquivos = ttk.Frame(self.detalhes, padding=4)
        self.tabela_arquivos = Tabela(aba_arquivos, ao_abrir=self._abrir_documento)
        self.tabela_arquivos.pack(fill="both", expand=True)
        self.detalhes.add(aba_arquivos, text="Arquivos")

        rodape = ttk.Frame(self, padding=(0, 6, 0, 0))
        rodape.pack(fill="x")
        self.var_resumo = tk.StringVar(value="Leia um diretório e clique em Contar páginas.")
        ttk.Label(rodape, textvariable=self.var_resumo, wraplength=760).pack(side="left")
        self.botoes_exportar = []
        for texto, extensao in (("Exportar XLSX", ".xlsx"), ("Exportar CSV", ".csv"), ("Exportar TXT", ".txt")):
            botao = ttk.Button(rodape, text=texto, state="disabled", command=lambda e=extensao: self._exportar(e))
            botao.pack(side="right", padx=(4, 0))
            self.botoes_exportar.append(botao)

    # ------------------------------------------------------------ catálogo
    def novo_catalogo(self, _catalogo: cat.Catalogo) -> None:
        self.resultado = None
        for tabela in (self.tabela_totais, self.tabela_problemas, self.tabela_arquivos):
            tabela.limpar()
        for cartao in (self.cartao_arquivos, self.cartao_paginas, self.cartao_erros,
                       self.cartao_problemas, self.cartao_tamanho):
            cartao.definir("—")
        for botao in self.botoes_exportar:
            botao.configure(state="disabled")
        self.var_resumo.set("Diretório lido. Escolha os tipos de arquivo e clique em Contar páginas.")
        self.var_info_problemas.set("")

    # ------------------------------------------------------------- contar
    def _opcoes(self) -> OpcoesContagem | None:
        extensoes = {e for exts, var in self.var_extensoes if var.get() for e in exts}
        if not extensoes:
            messagebox.showwarning(NOME, "Selecione ao menos um tipo de arquivo para contar.")
            return None
        de_texto, ate_texto = self.var_de.get().strip(), self.var_ate.get().strip()
        for texto in (de_texto, ate_texto):
            if not datas.periodo_valido(texto):
                messagebox.showerror(NOME, f"Data não reconhecida: {texto}\n\nUse 2019, 11/2019 ou 29/11/2019.")
                return None
        data_de = datas.limite_periodo(de_texto, inicio=True)
        data_ate = datas.limite_periodo(ate_texto, inicio=False)
        if data_de and data_ate and data_de > data_ate:
            messagebox.showerror(NOME, "A data inicial não pode ser depois da data final.")
            return None
        faltando = sorted({e for e in extensoes if not leitores.disponivel(e)})
        if faltando:
            if not messagebox.askyesno(
                NOME,
                f"Os componentes de leitura de {', '.join(faltando)} ainda não estão instalados; esses arquivos "
                "aparecerão como 'sem leitor'.\n\nContar assim mesmo?",
            ):
                return None
        return OpcoesContagem(
            extensoes=extensoes, data_de=data_de, data_ate=data_ate,
            base_data=ROTULOS_BASE.get(self.var_base.get(), cat.BASE_CRIACAO),
            aprofundada=self.var_aprofundada.get(),
        )

    def contar(self) -> None:
        opcoes = self._opcoes()
        if opcoes is None:
            return
        if self.app.catalogo_completo is None:
            # Quem veio só contar não precisa clicar em "Ler diretório" antes
            if self.app.var_diretorio.get().strip():
                self.app.ler_diretorio(depois=self.contar)
            else:
                messagebox.showwarning(NOME, "Escolha um diretório primeiro.")
            return
        catalogo = self.app.catalogo_completo

        def trabalho(progresso, cancelado):
            return contar(catalogo, opcoes, progresso, cancelado)

        self.app.executar("Contando páginas...", trabalho, self._mostrar)

    # ------------------------------------------------------------ resultado
    def _mostrar(self, resultado: ResultadoContagem) -> None:
        self.resultado = resultado
        self.cartao_arquivos.definir(formatar_inteiro(resultado.total_arquivos))
        self.cartao_paginas.definir(formatar_inteiro(resultado.total_paginas))
        self.cartao_erros.definir(formatar_inteiro(resultado.total_erros), destaque=bool(resultado.total_erros))
        self.cartao_problemas.definir(formatar_inteiro(resultado.total_problemas),
                                      destaque=bool(resultado.total_problemas))
        self.cartao_tamanho.definir(formatar_bytes(resultado.total_bytes))

        self._preencher_totais()
        self.tabela_problemas.preencher([
            ((p.categoria, p.arquivo, p.detalhe, p.caminho), "" if p.categoria == SEM_INDICE else "problema", p)
            for p in resultado.problemas
        ])
        por_categoria = resultado.problemas_por_categoria()
        self.var_info_problemas.set(
            " · ".join(f"{c}: {formatar_inteiro(n)}" for c, n in por_categoria) or "Nenhum problema encontrado."
        )
        self._preencher_arquivos()

        partes = [resultado.opcoes.descrever_tipos(), resultado.opcoes.descrever_periodo()]
        if resultado.fora_do_periodo:
            partes.append(f"{formatar_inteiro(resultado.fora_do_periodo)} fora do período")
        if resultado.cancelado:
            partes.append("CONTAGEM INTERROMPIDA — resultado parcial")
        self.var_resumo.set(" · ".join(partes))
        for botao in self.botoes_exportar:
            botao.configure(state="normal")
        self.detalhes.select(1 if resultado.total_problemas else 0)
        self.app.consulta.atualizar_totais()
        self.app.definir_status("Contagem concluída." if not resultado.cancelado else "Contagem interrompida.")

    def _preencher_totais(self) -> None:
        if self.resultado is None:
            return
        criterio = ROTULOS_AGRUPAMENTO.get(self.var_agrupamento.get(), "extensao")
        rotulo = AGRUPAMENTOS[criterio]
        self.tabela_totais.definir_colunas([rotulo, "Arquivos", "Páginas", "Com erro", "Tamanho"],
                                           {rotulo: 360, "Tamanho": 110}, 100,
                                           numericas={"Arquivos", "Páginas", "Com erro"})
        linhas = agrupar(self.resultado, criterio)
        dados = [((l.grupo, formatar_inteiro(l.arquivos), formatar_inteiro(l.paginas), formatar_inteiro(l.erros),
                   formatar_bytes(l.bytes)), "problema" if l.erros else "", l) for l in linhas]
        total = (("TOTAL", formatar_inteiro(self.resultado.total_arquivos), formatar_inteiro(self.resultado.total_paginas),
                  formatar_inteiro(self.resultado.total_erros), formatar_bytes(self.resultado.total_bytes)), "", None)
        self.tabela_totais.preencher(dados + [total])

    def _preencher_arquivos(self) -> None:
        resultado = self.resultado
        if resultado is None:
            return
        colunas = ["Arquivo", "Páginas", "No índice", "Situação", "Criado em", "Data interna", "Pasta"]
        if resultado.opcoes.aprofundada:
            colunas.insert(6, "PDF/A")
        self.tabela_arquivos.definir_colunas(
            colunas, {"Arquivo": 260, "Páginas": 70, "No índice": 70, "Situação": 140, "Criado em": 120,
                      "Data interna": 120, "PDF/A": 80, "Pasta": 360},
            numericas={"Páginas", "No índice"},
        )
        linhas = []
        for d in resultado.itens:
            pasta = caminho_relativo(d.caminho.parent if d.caminho else None, resultado.raiz)
            valores = [d.nome_arquivo, d.paginas_reais, d.paginas_indice,
                       d.estado if not d.divergente else "páginas divergentes",
                       datas.formatar_com_hora(d.data_criacao), datas.formatar_com_hora(d.data_interna),
                       "" if pasta == "." else pasta]
            if resultado.opcoes.aprofundada:
                valores.insert(6, d.pdfa or "—")
            etiqueta = "problema" if d.estado != leitores.OK else ("aviso" if d.divergente else "")
            linhas.append((tuple(valores), etiqueta, d))
        self.tabela_arquivos.preencher(linhas)

    # ---------------------------------------------------------- abrir
    def _abrir_documento(self, documento: cat.Documento) -> None:
        if documento.caminho:
            abrir_arquivo(str(documento.caminho))

    def _abrir_problema(self, problema) -> None:
        if problema.caminho:
            abrir_pasta_do_arquivo(problema.caminho)

    # -------------------------------------------------------- exportação
    def _exportar(self, extensao: str) -> None:
        if self.resultado is None:
            return
        tipos = {".txt": ("Texto", "*.txt"), ".csv": ("CSV (Excel)", "*.csv"), ".xlsx": ("Planilha Excel", "*.xlsx")}
        destino = filedialog.asksaveasfilename(title="Salvar relatório", defaultextension=extensao,
                                               filetypes=[tipos[extensao]], initialfile=f"contagem_ged{extensao}")
        if not destino:
            return
        incluir = self.app.catalogo_completo.incluir_subpastas if self.app.catalogo_completo else True
        try:
            exportar_contagem.exportar(destino, self.resultado, incluir)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Erro ao salvar", str(exc))
            return
        self.app.definir_status(f"Relatório salvo em {destino}")
        if messagebox.askyesno("Relatório salvo", f"Salvo em:\n{destino}\n\nAbrir agora?"):
            abrir_arquivo(destino)

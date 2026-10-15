"""Aba Consulta: a busca do GED Offline.

O formulário de busca e as colunas da tabela não existem até que um
diretório seja lido: eles são construídos a partir dos campos de índice
que os XML daquela pasta trouxerem. É isso que permite usar a mesma
ferramenta num acervo de despesas, de licitações ou de qualquer outra
natureza sem alterar o programa.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import NOME, catalogo as cat, datas, leitores
from ..busca import Criterios, a_ler_para_conteudo, buscar
from ..exportar import busca as exportar_busca
from ..texto import formatar_bytes, formatar_inteiro
from .dialogo_tipo import DialogoTipo, Escolha
from .sistema import abrir_arquivo, abrir_pasta_do_arquivo
from .widgets import COR_AVISO, COR_DICA, AreaRolavel, Tabela, dica

LARGURA_PREVIA = 230
FILTROS_POR_LINHA = 4
LIMITE_AVISO_CONTEUDO = 150
ATRASO_PREVIA_MS = 160
CAMPOS_ESTREITOS = ("numero", "num", "ano", "data", "valor", "tipo", "fonte", "paginas")

ROTULOS_BASE = {rotulo: chave for chave, rotulo in cat.BASES_DATA.items()}


class AbaConsulta(ttk.Frame):
    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(4, 6, 4, 4))
        self.app = app
        self.catalogo: cat.Catalogo | None = None
        self.grupos: list[cat.GrupoTipo] = []
        self.sem_tipo = 0
        self.contagem_indices: dict[str, int] = {}
        self.escolha: Escolha | None = None
        self._tipo_pendente = False
        self.resultado = None
        self.criterios_do_resultado = Criterios()
        self._filtros: dict[str, tk.StringVar] = {}
        self._imagem_previa = None
        self._fila_previa: queue.Queue = queue.Queue()
        self._ficha_previa = 0
        self._agendamento_previa = None
        self._montar()

    # ------------------------------------------------------------ montagem
    def _montar(self) -> None:
        quadro = ttk.LabelFrame(self, text="Busca", padding=(8, 4, 8, 6))
        quadro.pack(fill="x", pady=(0, 4))

        linha1 = ttk.Frame(quadro)
        linha1.pack(fill="x")
        self.botao_tipo = ttk.Button(linha1, text="Tipo: —", command=self.escolher_tipo, state="disabled")
        self.botao_tipo.pack(side="left", padx=(0, 10))
        ttk.Label(linha1, text="Texto:").pack(side="left")
        self.var_termo = tk.StringVar()
        entrada = ttk.Entry(linha1, textvariable=self.var_termo, width=28)
        entrada.pack(side="left", padx=(4, 10))
        entrada.bind("<Return>", lambda _e: self.buscar())

        self.var_escopo_nome = tk.BooleanVar(value=True)
        self.var_escopo_indice = tk.BooleanVar(value=True)
        self.var_escopo_conteudo = tk.BooleanVar(value=False)
        ttk.Checkbutton(linha1, text="nome", variable=self.var_escopo_nome).pack(side="left")
        ttk.Checkbutton(linha1, text="índice", variable=self.var_escopo_indice).pack(side="left", padx=6)
        ttk.Checkbutton(linha1, text="conteúdo do PDF", variable=self.var_escopo_conteudo).pack(side="left")

        ttk.Button(linha1, text="Buscar", command=self.buscar).pack(side="right")
        ttk.Button(linha1, text="Limpar", command=self._limpar).pack(side="right", padx=5)
        self.botao_precarregar = ttk.Button(linha1, text="Ler conteúdo de todos", command=self._precarregar,
                                            state="disabled")
        self.botao_precarregar.pack(side="right", padx=5)

        linha2 = ttk.Frame(quadro)
        linha2.pack(fill="x", pady=(5, 0))
        self.var_indice_de, self.var_indice_ate = tk.StringVar(), tk.StringVar()
        self.var_arquivo_de, self.var_arquivo_ate = tk.StringVar(), tk.StringVar()
        self._periodo(linha2, "Período do índice:", self.var_indice_de, self.var_indice_ate)
        self.rotulo_campo_data = dica(linha2, "")
        self.rotulo_campo_data.pack(side="left", padx=(4, 14))
        self.var_base = tk.StringVar(value=cat.BASES_DATA[cat.BASE_CRIACAO])
        ttk.Label(linha2, text="Data do arquivo:").pack(side="left", padx=(0, 4))
        ttk.Combobox(linha2, textvariable=self.var_base, values=list(cat.BASES_DATA.values()), width=20,
                     state="readonly").pack(side="left", padx=(0, 4))
        self._periodo(linha2, "", self.var_arquivo_de, self.var_arquivo_ate)
        dica(linha2, "aceita 2019, 11/2019 ou 29/11/2019").pack(side="left", padx=6)

        self.area_filtros = AreaRolavel(quadro)
        self.area_filtros.pack(fill="x", pady=(5, 0))
        self.quadro_filtros = self.area_filtros.interno
        ttk.Label(self.quadro_filtros, text="Os campos de busca aparecem aqui depois que um diretório for lido — "
                                            "eles vêm dos próprios índices XML da pasta.",
                  foreground=COR_DICA).pack(anchor="w")

        painel = ttk.PanedWindow(self, orient="horizontal")
        painel.pack(fill="both", expand=True)

        self.tabela = Tabela(painel, ao_abrir=self._abrir_documento)
        painel.add(self.tabela, weight=5)
        self.tabela.arvore.bind("<<TreeviewSelect>>", lambda _e: self._agendar_previa())
        self.tabela.arvore.bind("<Button-3>", self._menu_de_contexto)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Abrir arquivo", command=self._abrir_selecionado)
        self.menu.add_command(label="Abrir pasta do arquivo", command=self._abrir_pasta_selecionada)

        quadro_previa = ttk.LabelFrame(painel, text="Documento", padding=6)
        painel.add(quadro_previa, weight=1)
        self.rotulo_previa = ttk.Label(quadro_previa, text=self._texto_previa_inicial(), anchor="n",
                                       justify="center", wraplength=LARGURA_PREVIA)
        self.rotulo_previa.pack(fill="both", expand=True)
        self.var_ficha = tk.StringVar()
        ttk.Label(quadro_previa, textvariable=self.var_ficha, font=("", 8), justify="left",
                  wraplength=LARGURA_PREVIA).pack(fill="x", pady=(4, 2))
        ttk.Button(quadro_previa, text="Abrir arquivo", command=self._abrir_selecionado).pack(fill="x", pady=(4, 2))
        ttk.Button(quadro_previa, text="Abrir pasta do arquivo", command=self._abrir_pasta_selecionada).pack(fill="x")

        rodape = ttk.Frame(self, padding=(0, 5, 0, 0))
        rodape.pack(fill="x")
        self.var_total_diretorio = tk.StringVar(value="Diretório: —")
        self.var_total_resultado = tk.StringVar(value="Resultado: —")
        self.var_avisos = tk.StringVar(value="")
        ttk.Label(rodape, textvariable=self.var_total_diretorio).grid(row=0, column=0, sticky="w")
        ttk.Label(rodape, textvariable=self.var_total_resultado, font=("", 9, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(rodape, textvariable=self.var_avisos, foreground=COR_AVISO, font=("", 8),
                  wraplength=820).grid(row=2, column=0, sticky="w")
        rodape.columnconfigure(1, weight=1)
        self.botoes_exportar = []
        for coluna, (texto, extensao) in enumerate((("Exportar TXT", ".txt"), ("Exportar CSV", ".csv"),
                                                    ("Exportar XLSX", ".xlsx")), start=2):
            botao = ttk.Button(rodape, text=texto, state="disabled", command=lambda e=extensao: self._exportar(e))
            botao.grid(row=0, column=coluna, rowspan=3, padx=(4, 0))
            self.botoes_exportar.append(botao)

    @staticmethod
    def _periodo(master, rotulo: str, var_de: tk.StringVar, var_ate: tk.StringVar) -> None:
        if rotulo:
            ttk.Label(master, text=rotulo).pack(side="left")
        ttk.Entry(master, textvariable=var_de, width=11).pack(side="left", padx=(4, 2))
        ttk.Label(master, text="até").pack(side="left")
        ttk.Entry(master, textvariable=var_ate, width=11).pack(side="left", padx=2)

    @staticmethod
    def _texto_previa_inicial() -> str:
        if leitores.pdf_disponivel() and leitores.imagem_disponivel():
            return "Selecione um documento."
        return "Pré-visualização indisponível:\ncomponentes de leitura ainda não instalados."

    def dependencias_atualizadas(self) -> None:
        self.rotulo_previa.configure(text=self._texto_previa_inicial())
        if self.catalogo is not None:
            self.botao_precarregar.configure(state="normal" if leitores.pdf_disponivel() else "disabled")

    # ------------------------------------------------------------ catálogo
    def novo_catalogo(self, catalogo: cat.Catalogo) -> None:
        self.grupos, self.sem_tipo = cat.agrupar_por_tipo(catalogo)
        self.contagem_indices = cat.contagem_por_indice(catalogo)
        self.escolha = None  # pasta nova: a escolha anterior não vale mais
        self.botao_tipo.configure(state="normal")
        self.botao_precarregar.configure(state="normal" if leitores.pdf_disponivel() else "disabled")
        # Mostra já o tipo mais provável, para a tela não ficar vazia.
        self._aplicar_escolha(self._escolha_padrao())
        # A pergunta aparece sempre que a consulta estiver à vista: confirmar
        # é um Enter. Quem está só contando páginas não é interrompido.
        self._tipo_pendente = True
        if self.app.aba_consulta_ativa():
            self.after(50, self.ao_mostrar)

    def ao_mostrar(self) -> None:
        if self._tipo_pendente and self.app.catalogo_completo is not None:
            self._tipo_pendente = False
            self.escolher_tipo()

    def _escolha_padrao(self) -> Escolha:
        com_documentos = [g for g in self.grupos if g.total_documentos]
        if com_documentos:
            return Escolha(chave=max(com_documentos, key=lambda g: g.total_documentos).chave)
        return Escolha(chave=cat.TIPO_OUTRO)

    def escolher_tipo(self) -> None:
        if self.app.catalogo_completo is None:
            return
        atual = self.escolha or self._escolha_padrao()
        dialogo = DialogoTipo(self.app, self.grupos, self.sem_tipo, self.contagem_indices, atual)
        self.app.wait_window(dialogo)
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return  # a janela principal foi fechada com o diálogo aberto
        if dialogo.escolha is not None:
            self._aplicar_escolha(dialogo.escolha)

    def _aplicar_escolha(self, escolha: Escolha) -> None:
        completo = self.app.catalogo_completo
        if completo is None:
            return
        self.escolha = escolha
        if escolha.chave == cat.TIPO_OUTRO:
            self.catalogo = cat.subcatalogo_por_indices(completo, escolha.indices)
            quantos = len(self.catalogo.indices_escolhidos)
            self.botao_tipo.configure(text=f"Tipo: Outro ({quantos} índice{'s' if quantos != 1 else ''})")
        else:
            grupo = next(g for g in self.grupos if g.chave == escolha.chave)
            self.catalogo = cat.subcatalogo(completo, grupo)
            self.botao_tipo.configure(text=f"Tipo: {grupo.rotulo}")
        self._montar_filtros()
        self._montar_colunas()
        self.buscar()

    # ----------------------------------------------------- campos dinâmicos
    def _montar_filtros(self) -> None:
        for widget in self.quadro_filtros.winfo_children():
            widget.destroy()
        self._filtros.clear()
        campos_data = self.catalogo.campos_data if self.catalogo else []
        self.rotulo_campo_data.configure(text=f"({', '.join(campos_data)})" if campos_data else "(nenhum campo de data)")

        if not self.catalogo or not self.catalogo.vocabulario:
            ttk.Label(self.quadro_filtros, text="Nenhum campo de índice encontrado neste diretório — "
                                                "a busca por texto e por nome do arquivo continua funcionando.",
                      foreground=COR_DICA).pack(anchor="w")
            self.area_filtros.ajustar_altura()
            return

        for i, campo in enumerate(self.catalogo.vocabulario):
            linha, coluna = divmod(i, FILTROS_POR_LINHA)
            celula = ttk.Frame(self.quadro_filtros)
            celula.grid(row=linha, column=coluna, sticky="we", padx=(0, 10), pady=2)
            self.quadro_filtros.columnconfigure(coluna, weight=1)
            marca = " (data)" if campo in campos_data else ""
            ttk.Label(celula, text=campo + marca, font=("", 8)).pack(anchor="w")
            var = tk.StringVar()
            self._filtros[campo] = var
            entrada = ttk.Entry(celula, textvariable=var)
            entrada.pack(fill="x")
            entrada.bind("<Return>", lambda _e: self.buscar())
        self.area_filtros.ajustar_altura()

    def _montar_colunas(self) -> None:
        if not self.catalogo:
            return
        colunas = list(self.catalogo.vocabulario) + ["Páginas", "Arquivo", "Situação"]
        larguras = {c: self._largura(c) for c in colunas}
        self.tabela.definir_colunas(colunas, larguras, numericas={"Páginas"})

    @staticmethod
    def _largura(coluna: str) -> int:
        chave = coluna.lower()
        if chave == "arquivo":
            return 240
        if any(marca in chave for marca in CAMPOS_ESTREITOS):
            return 88
        return 140

    # -------------------------------------------------------------- busca
    def _criterios(self) -> Criterios:
        return Criterios(
            termo=self.var_termo.get(),
            escopo_nome=self.var_escopo_nome.get(),
            escopo_indice=self.var_escopo_indice.get(),
            escopo_conteudo=self.var_escopo_conteudo.get(),
            filtros={campo: var.get() for campo, var in self._filtros.items()},
            indice_de=self.var_indice_de.get(),
            indice_ate=self.var_indice_ate.get(),
            arquivo_de=self.var_arquivo_de.get(),
            arquivo_ate=self.var_arquivo_ate.get(),
            base_data_arquivo=ROTULOS_BASE.get(self.var_base.get(), cat.BASE_CRIACAO),
        )

    def buscar(self) -> None:
        if not self.catalogo:
            return
        criterios = self._criterios()
        invalidos = criterios.periodos_invalidos()
        if invalidos:
            messagebox.showwarning(NOME, f"Período não reconhecido: {', '.join(invalidos)}\n\n"
                                         "Use 2019, 11/2019 ou 29/11/2019.")
            return
        if criterios.base_data_arquivo == cat.BASE_INTERNA and (criterios.arquivo_de or criterios.arquivo_ate):
            sem_data = sum(1 for d in self.catalogo.documentos if d.localizado and d.data_interna is None)
            if sem_data:
                self.app.definir_status(
                    f"A data interna só é conhecida dos arquivos já abertos — {formatar_inteiro(sem_data)} "
                    "ainda sem ela. Use 'Contar páginas' na aba Contagem para ler todos."
                )
        self.criterios_do_resultado = criterios

        if not (criterios.escopo_conteudo and criterios.termo_limpo):
            self.resultado = buscar(self.catalogo, criterios)
            self._preencher_tabela()
            return

        if not leitores.pdf_disponivel():
            messagebox.showwarning("Busca por conteúdo indisponível",
                                   "A leitura do texto dos PDFs depende do componente pypdfium2, que ainda não "
                                   "foi instalado.\nA busca foi feita apenas no nome do arquivo e no índice.")
            self.var_escopo_conteudo.set(False)
            self.resultado = buscar(self.catalogo, self._criterios())
            self._preencher_tabela()
            return

        pendentes = a_ler_para_conteudo(self.catalogo, criterios, self.app.cache)
        if not pendentes:
            # Nada novo a abrir: já está tudo em memória. Responde na hora.
            self.resultado = buscar(self.catalogo, criterios, cache=self.app.cache)
            self._preencher_tabela()
            return

        if len(pendentes) > LIMITE_AVISO_CONTEUDO and not messagebox.askyesno(
            "Buscar dentro dos PDFs",
            f"Esta busca precisa abrir {formatar_inteiro(len(pendentes))} arquivo(s) ainda não lidos.\n\n"
            "Preencher antes um campo de índice ou um período reduz bastante essa leitura.\n\n"
            "Continuar assim mesmo?",
        ):
            return

        catalogo, cache = self.catalogo, self.app.cache

        def trabalho(progresso, cancelado):
            return buscar(catalogo, criterios, cache=cache,
                          progresso=lambda a, t, n: progresso(cat.Progresso("conteúdo", a, t, n)),
                          cancelado=cancelado)

        def concluir(resultado) -> None:
            self.resultado = resultado
            self._preencher_tabela()

        self.app.executar("Procurando dentro dos PDFs...", trabalho, concluir)

    def _precarregar(self) -> None:
        if not self.catalogo:
            return
        documentos = [d for d in self.catalogo.documentos
                      if d.localizado and d.extensao in leitores.EXTENSOES_PDF and not self.app.cache.ja_lido(d.caminho)]
        cache = self.app.cache

        def trabalho(progresso, cancelado):
            lidos = 0
            for i, documento in enumerate(documentos):
                if cancelado():
                    break
                progresso(cat.Progresso("conteúdo", i, len(documentos), documento.nome_arquivo))
                cache.texto(documento.caminho)
                lidos += 1
            return lidos

        def concluir(lidos: int) -> None:
            self.app.definir_status(f"Conteúdo lido de {formatar_inteiro(lidos)} PDF(s). "
                                    "As buscas por conteúdo agora são instantâneas.")

        self.app.executar(f"Lendo o conteúdo de {formatar_inteiro(len(documentos))} PDF(s)...", trabalho, concluir)

    def _limpar(self) -> None:
        self.var_termo.set("")
        for var in list(self._filtros.values()) + [self.var_indice_de, self.var_indice_ate,
                                                   self.var_arquivo_de, self.var_arquivo_ate]:
            var.set("")
        self.buscar()

    # ----------------------------------------------------------- tabela
    def _preencher_tabela(self) -> None:
        if not self.catalogo or self.resultado is None:
            self.tabela.limpar()
            return
        linhas = []
        for documento in self.resultado.documentos:
            valores = [documento.valor(c) for c in self.catalogo.vocabulario]
            valores.append(documento.paginas if documento.paginas is not None else "?")
            valores.append(documento.nome_arquivo)
            if not documento.localizado:
                situacao, etiqueta = "sem arquivo", "problema"
            elif documento.lido and documento.estado != leitores.OK:
                situacao, etiqueta = documento.estado, "problema"
            elif documento.divergente:
                situacao, etiqueta = "páginas divergentes", "aviso"
            else:
                situacao, etiqueta = "ok", ""
            valores.append(situacao)
            linhas.append((tuple(valores), etiqueta, documento))
        self.tabela.preencher(linhas)
        self.atualizar_totais()
        estado = "normal" if self.resultado.documentos else "disabled"
        for botao in self.botoes_exportar:
            botao.configure(state=estado)
        r = self.resultado
        if r.conteudo_usado:
            self.app.definir_status(f"Busca concluída — {formatar_inteiro(r.lidos_para_conteudo)} PDF(s) lidos, "
                                    f"{formatar_inteiro(r.achados_por_conteudo)} encontrados pelo conteúdo.")
        else:
            self.app.definir_status("Busca concluída.")

    def atualizar_totais(self) -> None:
        if not self.catalogo:
            return
        c = self.catalogo
        escopo = f"Tipo {c.tipo_ativo}" if c.tipo_ativo else "Diretório"
        self.var_total_diretorio.set(
            f"{escopo}: {formatar_inteiro(c.total_documentos)} documentos · {formatar_inteiro(c.total_paginas)} páginas"
            + (f" (+{c.paginas_desconhecidas} não contados)" if c.paginas_desconhecidas else "")
        )
        if self.resultado is None:
            return
        r = self.resultado
        self.var_total_resultado.set(
            f"Resultado: {formatar_inteiro(r.total_documentos)} documentos · {formatar_inteiro(r.total_paginas)} páginas"
            + (f" (+{r.paginas_desconhecidas} não contados)" if r.paginas_desconhecidas else "")
        )
        avisos = exportar_busca.observacoes(c, r)
        if r.paginas_desconhecidas:
            avisos = avisos[1:]  # já dito na linha do total
        self.var_avisos.set(" · ".join(avisos))

    # ---------------------------------------------------------- documento
    def _menu_de_contexto(self, evento) -> None:
        if self.tabela.selecionar_linha_em(evento.y):
            self.menu.tk_popup(evento.x_root, evento.y_root)

    def _sem_arquivo(self) -> None:
        messagebox.showwarning("Arquivo não localizado",
                               "Este registro veio de um índice XML, mas o arquivo correspondente "
                               "não está no diretório lido.")

    def _abrir_documento(self, documento: cat.Documento) -> None:
        if not documento.localizado:
            self._sem_arquivo()
            return
        abrir_arquivo(str(documento.caminho))

    def _abrir_selecionado(self) -> None:
        documento = self.tabela.selecionado()
        if documento:
            self._abrir_documento(documento)

    def _abrir_pasta_selecionada(self) -> None:
        documento = self.tabela.selecionado()
        if not documento:
            return
        if not documento.localizado:
            self._sem_arquivo()
            return
        abrir_pasta_do_arquivo(str(documento.caminho))

    # ------------------------------------------------------- pré-visualização
    def _agendar_previa(self) -> None:
        # Espera o usuário parar de navegar com as setas antes de abrir o arquivo
        if self._agendamento_previa is not None:
            self.after_cancel(self._agendamento_previa)
        self._agendamento_previa = self.after(ATRASO_PREVIA_MS, self._mostrar_previa)

    def _ficha(self, documento: cat.Documento) -> str:
        linhas = []
        if documento.paginas is not None:
            linhas.append(f"Páginas: {formatar_inteiro(documento.paginas)}")
        if documento.divergente:
            linhas.append(f"Índice informa {documento.paginas_indice} — arquivo tem {documento.paginas_reais}")
        if documento.tamanho:
            linhas.append(f"Tamanho: {formatar_bytes(documento.tamanho)}")
        if documento.data_criacao:
            linhas.append(f"Criado em: {datas.formatar_com_hora(documento.data_criacao)}")
        if documento.data_interna:
            linhas.append(f"Data interna: {datas.formatar_com_hora(documento.data_interna)}")
        if documento.erro:
            linhas.append(f"Situação: {documento.erro}")
        return "\n".join(linhas)

    def _mostrar_previa(self) -> None:
        self._agendamento_previa = None
        documento = self.tabela.selecionado()
        if not documento:
            return
        self._ficha_previa += 1
        ficha = self._ficha_previa
        self.var_ficha.set(self._ficha(documento))
        if not documento.localizado:
            self._imagem_previa = None
            self.rotulo_previa.configure(image="", text="(sem arquivo para pré-visualizar)")
            return
        if not leitores.imagem_disponivel():
            return
        self.rotulo_previa.configure(image="", text="Carregando...")
        caminho = documento.caminho
        # Gerar a miniatura de um PDF grande ou em rede leva tempo: fora da
        # thread da interface, para a janela não congelar.
        threading.Thread(
            target=lambda: self._fila_previa.put((ficha, leitores.miniatura_ppm(caminho, LARGURA_PREVIA))),
            daemon=True,
        ).start()
        self.after(40, self._receber_previa)

    def _receber_previa(self) -> None:
        try:
            ficha, dados = self._fila_previa.get_nowait()
        except queue.Empty:
            self.after(40, self._receber_previa)
            return
        if ficha != self._ficha_previa:
            # Miniatura de uma seleção antiga: descarta e espera a atual
            self.after(40, self._receber_previa)
            return
        if not dados:
            self._imagem_previa = None
            self.rotulo_previa.configure(image="", text="(não foi possível gerar a pré-visualização)")
            return
        self._imagem_previa = tk.PhotoImage(data=dados)
        self.rotulo_previa.configure(image=self._imagem_previa, text="")

    # -------------------------------------------------------- exportação
    def _exportar(self, extensao: str) -> None:
        if not self.catalogo or self.resultado is None or not self.resultado.documentos:
            return
        tipos = {".txt": ("Texto", "*.txt"), ".csv": ("CSV (Excel)", "*.csv"), ".xlsx": ("Planilha Excel", "*.xlsx")}
        destino = filedialog.asksaveasfilename(title="Salvar relatório", defaultextension=extensao,
                                               filetypes=[tipos[extensao]], initialfile=f"busca_ged{extensao}")
        if not destino:
            return
        try:
            exportar_busca.exportar(destino, self.catalogo, self.resultado, self.criterios_do_resultado)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Erro ao salvar", str(exc))
            return
        self.app.definir_status(f"Relatório salvo em {destino}")
        if messagebox.askyesno("Relatório salvo", f"Salvo em:\n{destino}\n\nAbrir agora?"):
            abrir_arquivo(destino)

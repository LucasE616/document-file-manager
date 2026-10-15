"""Relatórios da contagem e auditoria.

- TXT: legível, com resumo, totais por extensão e por tipo, os problemas
  agrupados por categoria e a lista de arquivos.
- CSV: só a tabela de arquivos, uma linha por arquivo. O contador antigo
  punha o resumo no topo do CSV, o que quebrava a tabela no Excel; o resumo
  agora fica no TXT e na aba "Resumo" do XLSX.
- XLSX: abas Resumo, Arquivos, Problemas e uma aba por agrupamento.
"""
from __future__ import annotations

from pathlib import Path

from .. import leitores
from ..catalogo import BASES_DATA, Documento
from ..contagem import AGRUPAMENTOS, SEM_INDICE, ResultadoContagem, agrupar, caminho_relativo
from ..texto import formatar_bytes, formatar_inteiro
from . import comum
from .xlsx import Planilha, escrever_xlsx


def _cabecalho(resultado: ResultadoContagem, incluir_subpastas: bool = True) -> list[tuple[str, str]]:
    opcoes = resultado.opcoes
    linhas = [
        ("Diretório", f"{resultado.raiz}  ({comum.escopo_pasta(incluir_subpastas)})"),
        ("Emitido em", resultado.emitido_em.strftime("%d/%m/%Y %H:%M")),
        ("Programa", comum.assinatura()),
        ("Tipos", opcoes.descrever_tipos()),
        ("Período", opcoes.descrever_periodo()),
        ("Conferência", "aprofundada (SHA-256, PDF/A declarado, integridade)" if opcoes.aprofundada else "rápida"),
    ]
    if resultado.hash_conjunto:
        linhas.append(("Hash do conjunto", resultado.hash_conjunto))
    if resultado.cancelado:
        linhas.append(("Atenção", "contagem interrompida antes do fim — resultado parcial"))
    return linhas


def _totais(resultado: ResultadoContagem) -> list[tuple[str, str]]:
    linhas = [
        ("Arquivos", formatar_inteiro(resultado.total_arquivos)),
        ("Páginas", formatar_inteiro(resultado.total_paginas)),
        ("Com erro", formatar_inteiro(resultado.total_erros)),
        ("Tamanho", formatar_bytes(resultado.total_bytes)),
        ("Problemas", formatar_inteiro(resultado.total_problemas)),
    ]
    if resultado.fora_do_periodo:
        linhas.append(("Fora do período", formatar_inteiro(resultado.fora_do_periodo)))
    return linhas


def _colunas(resultado: ResultadoContagem) -> list[str]:
    colunas = [
        "Arquivo", "Pasta", "Extensão", "Páginas", "Páginas no índice", "Situação", "Erro",
        "Tamanho (bytes)", "Criado em", "Modificado em", "Data interna", "Origem",
    ]
    if resultado.opcoes.aprofundada:
        colunas += ["PDF/A declarado", "SHA-256"]
    return colunas + ["Caminho completo"]


def _linha(d: Documento, resultado: ResultadoContagem) -> list:
    pasta = caminho_relativo(d.caminho.parent if d.caminho else None, resultado.raiz)
    linha = [
        d.nome_arquivo, "" if pasta == "." else pasta, d.extensao, d.paginas_reais, d.paginas_indice,
        d.estado, d.erro, d.tamanho, comum.data_hora(d.data_criacao), comum.data_hora(d.data_modificacao),
        comum.data_hora(d.data_interna), d.origem,
    ]
    if resultado.opcoes.aprofundada:
        linha += [d.pdfa, d.sha256]
    return linha + [str(d.caminho) if d.caminho else ""]


def exportar_csv(destino: Path | str, resultado: ResultadoContagem, incluir_subpastas: bool = True) -> Path:
    return comum.gravar_csv(destino, _colunas(resultado), [_linha(d, resultado) for d in resultado.itens])


def exportar_xlsx(destino: Path | str, resultado: ResultadoContagem, incluir_subpastas: bool = True) -> Path:
    resumo: list[list] = [["Contagem e auditoria do acervo", ""]]
    resumo += [[r, v] for r, v in _cabecalho(resultado, incluir_subpastas)]
    resumo.append(["", ""])
    resumo += [
        ["Arquivos", resultado.total_arquivos],
        ["Páginas", resultado.total_paginas],
        ["Com erro", resultado.total_erros],
        ["Tamanho (bytes)", resultado.total_bytes],
        ["Problemas", resultado.total_problemas],
        ["Fora do período", resultado.fora_do_periodo],
        ["", ""],
        ["Problemas por categoria", ""],
    ]
    resumo += [[c, n] for c, n in resultado.problemas_por_categoria()]
    planilhas = [
        Planilha("Resumo", resumo, negrito={0, len(resumo) - len(resultado.problemas_por_categoria()) - 1},
                 congelar_linhas=0, larguras=[42, 90]),
        Planilha("Arquivos", [_colunas(resultado)] + [_linha(d, resultado) for d in resultado.itens]),
        Planilha("Problemas", [["Categoria", "Arquivo", "Detalhe", "Caminho"]]
                 + [[p.categoria, p.arquivo, p.detalhe, p.caminho] for p in resultado.problemas]),
    ]
    for criterio, rotulo in AGRUPAMENTOS.items():
        if criterio == "pdfa" and not resultado.opcoes.aprofundada:
            continue
        linhas = [[rotulo, "Arquivos", "Páginas", "Com erro", "Tamanho (bytes)"]]
        linhas += [[l.grupo, l.arquivos, l.paginas, l.erros, l.bytes] for l in agrupar(resultado, criterio)]
        nome = "Por PDF-A declarado" if criterio == "pdfa" else f"Por {rotulo.lower()}"
        planilhas.append(Planilha(nome, linhas))
    return escrever_xlsx(destino, planilhas)


def _tabela_totais(resultado: ResultadoContagem, criterio: str) -> list[str]:
    linhas = agrupar(resultado, criterio)
    if not linhas:
        return []
    largura = min(max(len(l.grupo) for l in linhas), 40) + 2
    saida = [f"  {AGRUPAMENTOS[criterio].upper()}"]
    for l in linhas:
        nome = l.grupo if len(l.grupo) <= 40 else "…" + l.grupo[-39:]
        erros = f"   {formatar_inteiro(l.erros)} com erro" if l.erros else ""
        saida.append(
            f"    {nome.ljust(largura, '.')} {formatar_inteiro(l.arquivos).rjust(8)} arquivo(s)"
            f" {formatar_inteiro(l.paginas).rjust(10)} página(s){erros}"
        )
    return saida + [""]


def exportar_txt(destino: Path | str, resultado: ResultadoContagem, incluir_subpastas: bool = True) -> Path:
    partes: list[str] = [f"RELATÓRIO DE CONTAGEM E AUDITORIA — {comum.assinatura()}", ""]
    partes += [comum.linha_rotulada(r, v) for r, v in _cabecalho(resultado, incluir_subpastas)]
    partes += ["", comum.REGUA, "", "TOTAIS"]
    partes += [f"  {comum.linha_rotulada(r, v)}" for r, v in _totais(resultado)]
    partes.append("")
    for criterio in ("extensao", "tipo", "ano"):
        partes += _tabela_totais(resultado, criterio)
    if resultado.opcoes.aprofundada:
        partes += _tabela_totais(resultado, "pdfa")

    partes += [comum.REGUA, ""]
    if resultado.problemas:
        partes.append(f"PROBLEMAS ENCONTRADOS ({formatar_inteiro(resultado.total_problemas)})")
        partes.append("")
        for categoria, quantidade in resultado.problemas_por_categoria():
            marca = "(informativo) " if categoria == SEM_INDICE else ""
            partes.append(f"[{categoria}] {marca}— {formatar_inteiro(quantidade)}")
            for p in (x for x in resultado.problemas if x.categoria == categoria):
                partes.append(f"    {p.arquivo}" + (f" — {p.detalhe}" if p.detalhe else ""))
                if p.caminho:
                    partes.append(f"      {p.caminho}")
            partes.append("")
    else:
        partes += ["Nenhum problema encontrado.", ""]

    partes += [comum.REGUA, "", "ARQUIVOS", ""]
    partes.append(f"  {'Páginas'.rjust(8)}  {'Situação'.ljust(20)}  {'Criado em'.ljust(16)}  Arquivo")
    for d in resultado.itens:
        paginas = "—" if d.paginas_reais is None else formatar_inteiro(d.paginas_reais)
        situacao = d.estado if d.estado == leitores.OK else f"[{d.estado.upper()}]"
        partes.append(
            f"  {paginas.rjust(8)}  {situacao.ljust(20)}  {comum.data_hora(d.data_criacao).ljust(16)}"
            f"  {caminho_relativo(d.caminho, resultado.raiz)}"
        )
        if d.erro:
            partes.append(f"  {'':8}  {'':20}  {'':16}    ↳ {d.erro}")
    if resultado.opcoes.base_data != "criacao":
        partes += ["", f"Base do período: {BASES_DATA.get(resultado.opcoes.base_data)}"]
    return comum.gravar_txt(destino, partes)


EXPORTADORES = {".txt": exportar_txt, ".csv": exportar_csv, ".xlsx": exportar_xlsx}


def exportar(destino: Path | str, resultado: ResultadoContagem, incluir_subpastas: bool = True) -> Path:
    extensao = Path(destino).suffix.lower()
    funcao = EXPORTADORES.get(extensao)
    if funcao is None:
        raise ValueError(f"Formato não suportado: {extensao or '(sem extensão)'}. Use .txt, .csv ou .xlsx.")
    return funcao(destino, resultado, incluir_subpastas)

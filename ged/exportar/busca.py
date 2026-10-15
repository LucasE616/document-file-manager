"""Relatórios do resultado da consulta.

O CSV e o XLSX vão para a planilha; o TXT vai anexado ao processo. Todos
saem do mesmo resultado em tela e registram o que foi buscado.
"""
from __future__ import annotations

from pathlib import Path

from ..busca import Criterios, Resultado
from ..catalogo import Catalogo, Documento
from ..texto import formatar_inteiro
from . import comum
from .xlsx import Planilha, escrever_xlsx

COLUNAS_FIXAS = ["Arquivo", "Páginas", "Origem", "Arquivo localizado", "Data de criação", "Caminho"]


def _cabecalho(catalogo: Catalogo, criterios: Criterios) -> list[tuple[str, str]]:
    linhas = [
        ("Diretório", f"{catalogo.raiz}  ({comum.escopo_pasta(catalogo.incluir_subpastas)})"),
        ("Emitido em", comum.agora()),
        ("Programa", comum.assinatura()),
    ]
    if catalogo.tipo_ativo:
        linhas.append(("Tipo", catalogo.tipo_ativo))
    if catalogo.indices_escolhidos:
        linhas.append(("Índices", ", ".join(catalogo.indices_escolhidos)))
    linhas.append(("Escopo", criterios.escopos_descritos()))
    return linhas


def _linha(documento: Documento, vocabulario: list[str]) -> list:
    return [documento.valor(c) for c in vocabulario] + [
        documento.nome_arquivo,
        documento.paginas,
        documento.origem,
        "sim" if documento.localizado else "não",
        comum.data_hora(documento.data_criacao),
        str(documento.caminho) if documento.caminho else "",
    ]


def observacoes(catalogo: Catalogo, resultado: Resultado) -> list[str]:
    """Avisos que evitam que um total pareça mais completo do que é."""
    obs: list[str] = []
    if resultado.paginas_desconhecidas:
        obs.append(f"{resultado.paginas_desconhecidas} documento(s) sem contagem de páginas — fora do total acima")
    if resultado.sem_arquivo:
        obs.append(f"{resultado.sem_arquivo} documento(s) do índice sem arquivo localizado")
    if resultado.conteudo_usado and resultado.sem_texto:
        obs.append(f"{resultado.sem_texto} PDF(s) sem camada de texto — não havia o que procurar dentro")
    if resultado.conteudo_usado and resultado.nao_verificados:
        obs.append(
            f"{resultado.nao_verificados} documento(s) não puderam ser verificados por conteúdo: "
            "sem PDF no diretório"
        )
    if resultado.cancelado:
        obs.append("busca por conteúdo interrompida antes do fim — resultado parcial")
    if catalogo.xmls_tolerantes:
        obs.append(f"{len(catalogo.xmls_tolerantes)} índice(s) XML lido(s) em modo tolerante (arquivo malformado)")
    if catalogo.registros_duplicados:
        obs.append(f"{len(catalogo.registros_duplicados)} registro(s) duplicado(s) nos índices — contados uma vez")
    if catalogo.vinculos_ambiguos:
        obs.append(f"{catalogo.vinculos_ambiguos} arquivo(s) homônimo(s) vinculado(s) por aproximação")
    if catalogo.inacessiveis:
        obs.append(f"{len(catalogo.inacessiveis)} pasta(s) ou arquivo(s) inacessível(is)")
    return obs


def exportar_csv(destino: Path | str, catalogo: Catalogo, resultado: Resultado, criterios: Criterios) -> Path:
    """Uma coluna por índice descoberto no diretório, mais os campos do arquivo."""
    vocabulario = list(catalogo.vocabulario)
    return comum.gravar_csv(
        destino,
        vocabulario + COLUNAS_FIXAS,
        [_linha(d, vocabulario) for d in resultado.documentos],
    )


def exportar_xlsx(destino: Path | str, catalogo: Catalogo, resultado: Resultado, criterios: Criterios) -> Path:
    vocabulario = list(catalogo.vocabulario)
    tabela = Planilha("Resultado", [vocabulario + COLUNAS_FIXAS] + [_linha(d, vocabulario) for d in resultado.documentos])
    resumo_linhas: list[list] = [["Relatório de busca", ""]]
    resumo_linhas += [[r, v] for r, v in _cabecalho(catalogo, criterios)]
    resumo_linhas += [["Critérios", linha] for linha in criterios.descrever()]
    resumo_linhas += [
        ["Documentos", resultado.total_documentos],
        ["Páginas", resultado.total_paginas],
    ]
    resumo_linhas += [["Observação", o] for o in observacoes(catalogo, resultado)]
    resumo = Planilha("Resumo", resumo_linhas, congelar_linhas=0, larguras=[18, 100])
    return escrever_xlsx(destino, [resumo, tabela])


def exportar_txt(destino: Path | str, catalogo: Catalogo, resultado: Resultado, criterios: Criterios) -> Path:
    partes: list[str] = [f"RELATÓRIO DE BUSCA — {comum.assinatura()}", ""]
    for rotulo, valor in _cabecalho(catalogo, criterios):
        partes.append(comum.linha_rotulada(rotulo, valor, 14))

    criterios_descritos = criterios.descrever()
    partes.append(comum.linha_rotulada("Critérios", criterios_descritos[0], 14))
    for linha in criterios_descritos[1:]:
        partes.append(f"{' ' * 15}{linha}")

    partes.extend(["", comum.REGUA, ""])

    if not resultado.documentos:
        partes.append("Nenhum documento encontrado para estes critérios.")
    else:
        rotulos = list(catalogo.vocabulario)
        preenchimento = max((len(r) for r in rotulos), default=10) + 2
        preenchimento = max(preenchimento, len("Situação") + 2)
        for i, documento in enumerate(resultado.documentos, start=1):
            partes.append(f"{str(i).rjust(4)}. {documento.nome_arquivo}")
            for campo in rotulos:
                valor = documento.valor(campo).strip()
                if valor:
                    partes.append(f"      {campo.ljust(preenchimento, '.')} {valor}")
            paginas = documento.paginas
            partes.append(
                f"      {'Páginas'.ljust(preenchimento, '.')} "
                f"{paginas if paginas is not None else 'não contadas'}"
            )
            if not documento.localizado:
                partes.append(f"      {'Situação'.ljust(preenchimento, '.')} arquivo não localizado")
            partes.append("")

    partes.extend([comum.REGUA, ""])
    partes.append(
        f"TOTAL  {formatar_inteiro(resultado.total_documentos)} documento(s)"
        f"   {formatar_inteiro(resultado.total_paginas)} página(s)"
    )
    for observacao in observacoes(catalogo, resultado):
        partes.append(f"       {observacao}")
    return comum.gravar_txt(destino, partes)


EXPORTADORES = {".txt": exportar_txt, ".csv": exportar_csv, ".xlsx": exportar_xlsx}


def exportar(destino: Path | str, catalogo: Catalogo, resultado: Resultado, criterios: Criterios) -> Path:
    """Escolhe o formato pela extensão do destino."""
    extensao = Path(destino).suffix.lower()
    funcao = EXPORTADORES.get(extensao)
    if funcao is None:
        raise ValueError(f"Formato não suportado: {extensao or '(sem extensão)'}. Use .txt, .csv ou .xlsx.")
    return funcao(destino, catalogo, resultado, criterios)

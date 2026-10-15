"""Busca sobre o catálogo em memória.

Duas coisas diferentes acontecem aqui, e a distinção é o que faz a busca se
comportar como o usuário espera:

Os **filtros por campo** restringem — valem todos ao mesmo tempo, em E.
Preencher "Favorecido = CEMIG" tira da frente tudo que não for da CEMIG.

O **texto livre** amplia — vale em OU entre os escopos marcados. Um
documento entra no resultado se o termo aparecer no nome do arquivo, ou nos
índices, ou dentro do PDF. Por isso marcar "conteúdo do PDF" acrescenta
resultados em vez de cortar.

A economia vem daí naturalmente: só precisam ser abertos os PDFs dos
documentos que ainda não casaram pelo nome nem pelo índice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from . import datas
from .catalogo import BASE_CRIACAO, BASES_DATA, Catalogo, Documento
from .leitores import EXTENSOES_PDF
from .texto import contem, normalizar


@dataclass
class Criterios:
    termo: str = ""
    escopo_nome: bool = True
    escopo_indice: bool = True
    escopo_conteudo: bool = False
    filtros: dict[str, str] = field(default_factory=dict)
    # Período sobre o campo de data do índice (Data de Pagto, Data Ass...)
    indice_de: str = ""
    indice_ate: str = ""
    # Período sobre a data do arquivo (criação, modificação ou interna)
    arquivo_de: str = ""
    arquivo_ate: str = ""
    base_data_arquivo: str = BASE_CRIACAO

    @property
    def termo_limpo(self) -> str:
        return self.termo.strip()

    def periodo_indice(self) -> tuple[date | None, date | None]:
        return (
            datas.limite_periodo(self.indice_de, inicio=True),
            datas.limite_periodo(self.indice_ate, inicio=False),
        )

    def periodo_arquivo(self) -> tuple[date | None, date | None]:
        return (
            datas.limite_periodo(self.arquivo_de, inicio=True),
            datas.limite_periodo(self.arquivo_ate, inicio=False),
        )

    def periodos_invalidos(self) -> list[str]:
        """Períodos digitados que não são datas — para avisar em vez de ignorar."""
        return [
            texto
            for texto in (self.indice_de, self.indice_ate, self.arquivo_de, self.arquivo_ate)
            if not datas.periodo_valido(texto)
        ]

    def descrever(self) -> list[str]:
        """Critérios em texto, para o cabeçalho do relatório."""
        linhas: list[str] = []
        for campo, valor in self.filtros.items():
            if valor.strip():
                linhas.append(f'{campo} contém "{valor.strip()}"')
        rotulo_arquivo = BASES_DATA.get(self.base_data_arquivo, "data do arquivo")
        for rotulo, (de, ate) in (
            ("data do índice", self.periodo_indice()),
            (rotulo_arquivo, self.periodo_arquivo()),
        ):
            if de and ate:
                linhas.append(f"{rotulo} entre {datas.formatar(de)} e {datas.formatar(ate)}")
            elif de:
                linhas.append(f"{rotulo} a partir de {datas.formatar(de)}")
            elif ate:
                linhas.append(f"{rotulo} até {datas.formatar(ate)}")
        if self.termo_limpo:
            linhas.append(f'texto contém "{self.termo_limpo}"')
        return linhas or ["nenhum — todos os documentos do diretório"]

    def escopos_descritos(self) -> str:
        ativos = []
        if self.escopo_nome:
            ativos.append("nome do arquivo")
        if self.escopo_indice:
            ativos.append("índice XML")
        if self.escopo_conteudo:
            ativos.append("conteúdo do PDF")
        return " ou ".join(ativos) or "nenhum escopo marcado"


@dataclass
class Resultado:
    documentos: list[Documento] = field(default_factory=list)
    conteudo_usado: bool = False
    lidos_para_conteudo: int = 0
    achados_por_conteudo: int = 0
    sem_texto: int = 0
    # Documentos que não casaram pelo nome nem pelo índice e cujo PDF não
    # está no diretório: não dá para afirmar nada sobre o conteúdo deles.
    nao_verificados: int = 0
    cancelado: bool = False

    @property
    def total_documentos(self) -> int:
        return len(self.documentos)

    @property
    def total_paginas(self) -> int:
        return sum(d.paginas or 0 for d in self.documentos)

    @property
    def paginas_desconhecidas(self) -> int:
        return sum(1 for d in self.documentos if d.paginas is None)

    @property
    def sem_arquivo(self) -> int:
        return sum(1 for d in self.documentos if not d.localizado)

    sem_pdf = sem_arquivo


def _campo_casa(consulta: str, valor: str, eh_data: bool) -> bool:
    """Compara um campo com o que foi digitado.

    Nos campos de data, tenta primeiro como data: procurar "29/11/2019"
    encontra "2019-11-29", e "11/2019" encontra o mês inteiro. Nos demais
    a comparação é sempre por trecho de texto — antes, "05/2019" digitado
    no campo Número casava com o empenho "12052019" como se fosse data.
    """
    if eh_data:
        como_data = datas.casa_como_data(consulta, valor)
        if como_data is not None:
            return como_data
    return contem(consulta, valor)


def _dentro_do_periodo(alvo: date | None, de: date | None, ate: date | None) -> bool:
    if de is None and ate is None:
        return True
    if alvo is None:
        return False
    if de is not None and alvo < de:
        return False
    if ate is not None and alvo > ate:
        return False
    return True


class _Filtro:
    """Os critérios já interpretados — uma vez por busca, não uma vez por documento."""

    def __init__(self, criterios: Criterios, campos_data: list[str]) -> None:
        self.campos_data = list(campos_data)
        datas_set = set(campos_data)
        self.filtros = [
            (campo, valor.strip(), campo in datas_set)
            for campo, valor in criterios.filtros.items()
            if valor.strip()
        ]
        self.indice_de, self.indice_ate = criterios.periodo_indice()
        self.arquivo_de, self.arquivo_ate = criterios.periodo_arquivo()
        self.base = criterios.base_data_arquivo

    def passa(self, documento: Documento) -> bool:
        for campo, valor, eh_data in self.filtros:
            if not _campo_casa(valor, documento.valor(campo), eh_data):
                return False

        if self.indice_de or self.indice_ate:
            # Basta um dos campos de data do documento cair no período.
            candidatas = (datas.interpretar(documento.valor(c)) for c in self.campos_data)
            if not any(
                _dentro_do_periodo(d, self.indice_de, self.indice_ate)
                for d in candidatas if d is not None
            ):
                return False

        if self.arquivo_de or self.arquivo_ate:
            momento = documento.data_arquivo(self.base)
            if not _dentro_do_periodo(momento.date() if momento else None, self.arquivo_de, self.arquivo_ate):
                return False

        return True


def _casa_metadados(documento: Documento, criterios: Criterios, termo_norm: str) -> bool:
    """Termo livre no nome ou no índice — os escopos que não custam nada."""
    if criterios.escopo_nome and termo_norm in documento.nome_normalizado():
        return True
    if criterios.escopo_indice and termo_norm in documento.indice_normalizado():
        return True
    return False


def filtrados(catalogo: Catalogo, criterios: Criterios) -> list[Documento]:
    """Só os filtros por campo e por período, sem o termo livre."""
    filtro = _Filtro(criterios, catalogo.campos_data)
    return [d for d in catalogo.documentos if filtro.passa(d)]


def _pode_ler_conteudo(documento: Documento) -> bool:
    return documento.localizado and documento.extensao in EXTENSOES_PDF


def a_ler_para_conteudo(catalogo: Catalogo, criterios: Criterios, cache=None) -> list[Documento]:
    """Quais PDFs a busca por conteúdo precisaria abrir agora.

    Serve para avisar o usuário antes de uma leitura demorada: exclui os
    que já casaram por nome ou índice, os que não têm PDF no diretório e
    os que já foram lidos nesta sessão.
    """
    if not criterios.escopo_conteudo or not criterios.termo_limpo:
        return []
    termo_norm = normalizar(criterios.termo_limpo)
    pendentes = [
        d
        for d in filtrados(catalogo, criterios)
        if _pode_ler_conteudo(d) and not _casa_metadados(d, criterios, termo_norm)
    ]
    if cache is not None:
        pendentes = [d for d in pendentes if not cache.ja_lido(d.caminho)]
    return pendentes


def buscar(
    catalogo: Catalogo,
    criterios: Criterios,
    cache=None,
    progresso: Callable[[int, int, str], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Resultado:
    base = filtrados(catalogo, criterios)

    if not criterios.termo_limpo:
        return Resultado(documentos=base)

    termo_norm = normalizar(criterios.termo_limpo)
    marcados = [_casa_metadados(d, criterios, termo_norm) for d in base]

    usar_conteudo = criterios.escopo_conteudo and cache is not None
    if not usar_conteudo:
        return Resultado(documentos=[d for d, ok in zip(base, marcados) if ok])

    # Só abre os PDFs que ainda não casaram por nome nem por índice.
    pendentes = [(i, d) for i, (d, ok) in enumerate(zip(base, marcados)) if not ok]
    legiveis = [(i, d) for i, d in pendentes if _pode_ler_conteudo(d)]

    resultado = Resultado(conteudo_usado=True, nao_verificados=len(pendentes) - len(legiveis))
    caminhos_lidos: list[str] = []

    for posicao, (indice, documento) in enumerate(legiveis):
        if cancelado is not None and cancelado():
            resultado.cancelado = True
            break
        if progresso:
            progresso(posicao, len(legiveis), documento.nome_arquivo)
        texto = cache.texto(documento.caminho)
        caminhos_lidos.append(str(documento.caminho))
        resultado.lidos_para_conteudo += 1
        if termo_norm in texto:
            marcados[indice] = True
            resultado.achados_por_conteudo += 1

    resultado.sem_texto = cache.sem_texto(caminhos_lidos)
    resultado.documentos = [d for d, ok in zip(base, marcados) if ok]
    return resultado

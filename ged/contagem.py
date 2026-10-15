"""Contagem de páginas e auditoria do acervo.

É o antigo Contador de Páginas, agora sobre o mesmo catálogo da consulta.
Ele abre cada arquivo dos tipos escolhidos, conta as páginas de verdade e,
porque conhece também os índices XML, aponta o que não fecha:

- páginas do índice diferentes das páginas reais do arquivo
- registro de índice sem arquivo, e arquivo sem índice
- registro duplicado (o mesmo arquivo citado em mais de um XML)
- arquivo homônimo vinculado por aproximação
- arquivo corrompido, protegido por senha, sem páginas ou inacessível
- conteúdo idêntico em arquivos diferentes (na conferência aprofundada)

Nada é gravado: o resultado fica em memória até ser exportado.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from . import leitores
from .catalogo import (
    BASE_CRIACAO, BASE_INTERNA, BASES_DATA, ORIGEM_NOME, Catalogo, Documento, Progresso, classificar,
)
from . import perfil as perfis

# Categorias de problema, na ordem em que aparecem no relatório
DIVERGENCIA = "Páginas do índice diferentes do arquivo"
INDICE_SEM_ARQUIVO = "Registro de índice sem arquivo"
SEM_INDICE = "Arquivo sem registro de índice"
DUPLICADO_INDICE = "Registro duplicado no índice"
VINCULO_INCERTO = "Arquivo homônimo vinculado por aproximação"
ERRO_LEITURA = "Arquivo corrompido ou ilegível"
PROTEGIDO = "Protegido por senha"
SEM_PAGINAS = "Arquivo sem páginas"
INACESSIVEL = "Inacessível"
SEM_LEITOR = "Componente de leitura ausente"
CONTEUDO_IDENTICO = "Conteúdo idêntico a outro arquivo"
DATA_ILEGIVEL = "Data do arquivo desconhecida"
XML_TOLERANTE = "Índice XML malformado (lido em modo tolerante)"
XML_FALHA = "Índice XML que não pôde ser lido"

ORDEM_CATEGORIAS = [
    ERRO_LEITURA, PROTEGIDO, SEM_PAGINAS, INACESSIVEL, SEM_LEITOR,
    DIVERGENCIA, INDICE_SEM_ARQUIVO, DUPLICADO_INDICE, VINCULO_INCERTO,
    CONTEUDO_IDENTICO, DATA_ILEGIVEL, XML_FALHA, XML_TOLERANTE, SEM_INDICE,
]

_CATEGORIA_DO_ESTADO = {
    leitores.ERRO: ERRO_LEITURA,
    leitores.PROTEGIDO: PROTEGIDO,
    leitores.VAZIO: SEM_PAGINAS,
    leitores.INACESSIVEL: INACESSIVEL,
    leitores.SEM_LEITOR: SEM_LEITOR,
}

# Critérios de agrupamento dos totais
AGRUPAMENTOS = {
    "extensao": "Extensão",
    "tipo": "Tipo documental",
    "pasta": "Pasta",
    "ano": "Ano",
    "mes": "Mês",
    "situacao": "Situação",
    "pdfa": "PDF/A declarado",
}


@dataclass
class OpcoesContagem:
    extensoes: set[str] = field(default_factory=lambda: set(leitores.EXTENSOES_PADRAO))
    data_de: date | None = None
    data_ate: date | None = None
    base_data: str = BASE_CRIACAO
    # Lê cada arquivo por inteiro: SHA-256, PDF/A declarado e integridade
    # das imagens. Bem mais lento — por isso opcional.
    aprofundada: bool = False

    @property
    def tem_periodo(self) -> bool:
        return self.data_de is not None or self.data_ate is not None

    def descrever_tipos(self) -> str:
        rotulos = [r for r, exts in leitores.FORMATOS if set(exts) & self.extensoes]
        return ", ".join(rotulos) or "nenhum"

    def descrever_periodo(self) -> str:
        de = self.data_de.strftime("%d/%m/%Y") if self.data_de else ""
        ate = self.data_ate.strftime("%d/%m/%Y") if self.data_ate else ""
        base = BASES_DATA.get(self.base_data, self.base_data)
        if de and ate:
            return f"{base} de {de} até {ate}"
        if de:
            return f"{base} a partir de {de}"
        if ate:
            return f"{base} até {ate}"
        return "sem filtro de período"


@dataclass
class Problema:
    categoria: str
    arquivo: str
    detalhe: str = ""
    caminho: str = ""


@dataclass
class ResultadoContagem:
    raiz: Path
    opcoes: OpcoesContagem
    itens: list[Documento] = field(default_factory=list)
    problemas: list[Problema] = field(default_factory=list)
    fora_do_periodo: int = 0
    cancelado: bool = False
    emitido_em: datetime = field(default_factory=datetime.now)
    # SHA-256 da lista "hash  caminho" de todos os arquivos: permite provar,
    # depois, que o conjunto contado é exatamente este.
    hash_conjunto: str = ""

    @property
    def total_arquivos(self) -> int:
        return len(self.itens)

    @property
    def total_paginas(self) -> int:
        return sum(d.paginas_reais or 0 for d in self.itens)

    @property
    def total_bytes(self) -> int:
        return sum(d.tamanho for d in self.itens)

    @property
    def com_erro(self) -> list[Documento]:
        return [d for d in self.itens if d.estado != leitores.OK]

    @property
    def total_erros(self) -> int:
        return len(self.com_erro)

    def problemas_por_categoria(self) -> list[tuple[str, int]]:
        contagem = Counter(p.categoria for p in self.problemas)
        return [(c, contagem[c]) for c in ORDEM_CATEGORIAS if contagem.get(c)]

    @property
    def total_problemas(self) -> int:
        # "Arquivo sem índice" é informativo: num acervo sem XML, todo
        # arquivo seria um "problema".
        return sum(1 for p in self.problemas if p.categoria != SEM_INDICE)


def aplicar_leitura(documento: Documento, aprofundada: bool = False) -> None:
    """Abre o arquivo do documento e guarda páginas, estado e data interna."""
    if documento.caminho is None:
        return
    leitura = leitores.ler(documento.caminho, documento.extensao, verificar_imagem=aprofundada)
    documento.paginas_reais = leitura.paginas
    documento.estado = leitura.estado
    documento.erro = leitura.erro
    if leitura.data_interna:
        documento.data_interna = leitura.data_interna
    if aprofundada and leitura.estado not in (leitores.INACESSIVEL,):
        conferencia = leitores.conferir(documento.caminho, procurar_pdfa=documento.extensao in leitores.EXTENSOES_PDF)
        documento.sha256 = conferencia.sha256
        documento.pdfa = conferencia.pdfa


def ler_documentos(
    documentos: list[Documento],
    aprofundada: bool = False,
    progresso: Callable[[Progresso], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
    fase: str = "contando",
) -> int:
    """Lê os documentos indicados. Devolve quantos foram lidos antes de parar."""
    lidos = 0
    for i, documento in enumerate(documentos):
        if cancelado is not None and cancelado():
            break
        if progresso:
            progresso(Progresso(fase, i, len(documentos), documento.nome_arquivo))
        aplicar_leitura(documento, aprofundada)
        lidos += 1
    if progresso:
        progresso(Progresso(fase, len(documentos), len(documentos), "Concluído"))
    return lidos


def ler_paginas_faltantes(catalogo: Catalogo, progresso=None, cancelado=None) -> int:
    """Conta as páginas dos arquivos que nenhum índice informa.

    É a única leitura feita logo depois da varredura, em segundo plano,
    para que o total de páginas da consulta não fique incompleto.
    """
    pendentes = [d for d in catalogo.documentos if d.localizado and d.paginas is None and not d.lido]
    return ler_documentos(pendentes, progresso=progresso, cancelado=cancelado, fase="páginas")


def _no_periodo(documento: Documento, opcoes: OpcoesContagem) -> bool | None:
    """True/False, ou None quando o documento não tem a data pedida."""
    momento = documento.data_arquivo(opcoes.base_data)
    if momento is None:
        return None
    dia = momento.date()
    if opcoes.data_de and dia < opcoes.data_de:
        return False
    if opcoes.data_ate and dia > opcoes.data_ate:
        return False
    return True


def contar(
    catalogo: Catalogo,
    opcoes: OpcoesContagem,
    progresso: Callable[[Progresso], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> ResultadoContagem:
    resultado = ResultadoContagem(raiz=catalogo.raiz, opcoes=opcoes)
    extensoes = {e.lower() for e in opcoes.extensoes}
    candidatos = [d for d in catalogo.documentos if d.localizado and d.extensao in extensoes]

    problemas = resultado.problemas
    sem_data: list[Documento] = []

    # A data interna só se conhece abrindo o PDF: nesse caso lê primeiro e
    # filtra depois. Para as datas do disco, filtra antes e lê menos.
    if opcoes.tem_periodo and opcoes.base_data != BASE_INTERNA:
        selecionados = []
        for d in candidatos:
            dentro = _no_periodo(d, opcoes)
            if dentro is None:
                sem_data.append(d)
            elif dentro:
                selecionados.append(d)
            else:
                resultado.fora_do_periodo += 1
        candidatos = selecionados

    lidos = ler_documentos(candidatos, opcoes.aprofundada, progresso, cancelado)
    if lidos < len(candidatos):
        resultado.cancelado = True
        candidatos = candidatos[:lidos]

    if opcoes.tem_periodo and opcoes.base_data == BASE_INTERNA:
        selecionados = []
        for d in candidatos:
            dentro = _no_periodo(d, opcoes)
            if dentro is None:
                sem_data.append(d)
            elif dentro:
                selecionados.append(d)
            else:
                resultado.fora_do_periodo += 1
        candidatos = selecionados

    resultado.itens = candidatos

    # --- problemas de cada arquivo
    for d in candidatos:
        caminho = str(d.caminho)
        if d.estado != leitores.OK:
            problemas.append(Problema(_CATEGORIA_DO_ESTADO.get(d.estado, ERRO_LEITURA), d.nome_arquivo, d.erro, caminho))
        if d.divergente:
            problemas.append(Problema(
                DIVERGENCIA, d.nome_arquivo,
                f"índice diz {d.paginas_indice}, arquivo tem {d.paginas_reais}", caminho,
            ))
        if d.vinculo_ambiguo:
            problemas.append(Problema(
                VINCULO_INCERTO, d.nome_arquivo,
                f"há outros arquivos com este nome; índice: {d.xml_origem}", caminho,
            ))
        if d.origem == ORIGEM_NOME and catalogo.xmls_lidos:
            problemas.append(Problema(SEM_INDICE, d.nome_arquivo, "nenhum XML da pasta cita este arquivo", caminho))

    rotulo_base = BASES_DATA.get(opcoes.base_data, opcoes.base_data)
    for d in sem_data:
        problemas.append(Problema(DATA_ILEGIVEL, d.nome_arquivo, f"sem {rotulo_base}; fora da contagem", str(d.caminho)))

    # --- problemas do índice, que não dependem de abrir arquivo
    for d in catalogo.documentos:
        if not d.localizado and (not d.extensao or d.extensao in extensoes):
            problemas.append(Problema(INDICE_SEM_ARQUIVO, d.nome_arquivo or "(sem nome)", f"citado em {d.xml_origem}", ""))
    for dup in catalogo.registros_duplicados:
        detalhe = f"também em {dup.xml_mantido}"
        if dup.campos_diferentes:
            detalhe += " — com campos diferentes"
        problemas.append(Problema(DUPLICADO_INDICE, dup.nome_arquivo, detalhe, dup.xml_descartado))
    for xml in catalogo.xmls_tolerantes:
        problemas.append(Problema(XML_TOLERANTE, Path(xml).name, "valores podem estar truncados", xml))
    for xml, erro in catalogo.xmls_com_falha:
        problemas.append(Problema(XML_FALHA, Path(xml).name, erro, xml))
    ja_relatados = {p.caminho for p in problemas if p.categoria == INACESSIVEL}
    for caminho, erro in catalogo.inacessiveis:
        if caminho not in ja_relatados:
            problemas.append(Problema(INACESSIVEL, Path(caminho).name, erro, caminho))

    # --- conferência aprofundada: conteúdo repetido e hash do conjunto
    if opcoes.aprofundada:
        por_hash: dict[str, list[Documento]] = defaultdict(list)
        for d in candidatos:
            if d.sha256:
                por_hash[d.sha256].append(d)
        for iguais in por_hash.values():
            for repetido in iguais[1:]:
                problemas.append(Problema(
                    CONTEUDO_IDENTICO, repetido.nome_arquivo,
                    f"idêntico a {caminho_relativo(iguais[0].caminho, catalogo.raiz)}", str(repetido.caminho),
                ))
        linhas = sorted(f"{d.sha256}  {caminho_relativo(d.caminho, catalogo.raiz)}" for d in candidatos if d.sha256)
        resultado.hash_conjunto = hashlib.sha256("\n".join(linhas).encode("utf-8")).hexdigest()

    ordem = {c: i for i, c in enumerate(ORDEM_CATEGORIAS)}
    problemas.sort(key=lambda p: (ordem.get(p.categoria, 99), p.arquivo.lower()))
    return resultado


def caminho_relativo(caminho: Path | None, raiz: Path) -> str:
    if caminho is None:
        return ""
    try:
        return str(caminho.relative_to(raiz))
    except ValueError:
        return str(caminho)


@dataclass
class LinhaTotal:
    grupo: str
    arquivos: int = 0
    paginas: int = 0
    erros: int = 0
    bytes: int = 0


def agrupar(resultado: ResultadoContagem, criterio: str) -> list[LinhaTotal]:
    """Totais de arquivos, páginas e erros por um critério (ver AGRUPAMENTOS)."""
    linhas: dict[str, LinhaTotal] = {}
    perfil = perfis.ativo()
    for d in resultado.itens:
        chave = _chave_grupo(d, criterio, resultado, perfil)
        linha = linhas.setdefault(chave, LinhaTotal(chave))
        linha.arquivos += 1
        linha.paginas += d.paginas_reais or 0
        linha.bytes += d.tamanho
        if d.estado != leitores.OK:
            linha.erros += 1
    return sorted(linhas.values(), key=lambda l: (l.grupo.startswith("("), l.grupo.lower()))


def _chave_grupo(d: Documento, criterio: str, resultado: ResultadoContagem, perfil) -> str:
    if criterio == "extensao":
        return d.extensao or "(sem extensão)"
    if criterio == "tipo":
        chave = classificar(d, resultado.raiz)
        return perfil.rotulo(chave) if chave != "outro" else "Outros"
    if criterio == "pasta":
        relativo = caminho_relativo(d.caminho.parent if d.caminho else None, resultado.raiz)
        return relativo if relativo not in ("", ".") else "(pasta raiz)"
    if criterio in ("ano", "mes"):
        momento = d.data_arquivo(resultado.opcoes.base_data)
        if momento is None:
            return "(sem data)"
        return momento.strftime("%Y") if criterio == "ano" else momento.strftime("%Y-%m")
    if criterio == "situacao":
        return d.estado or "não lido"
    if criterio == "pdfa":
        if not resultado.opcoes.aprofundada:
            return "(use a conferência aprofundada)"
        return d.pdfa or "não declarado"
    raise ValueError(f"Agrupamento desconhecido: {criterio}")

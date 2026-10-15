"""Varredura do diretório e catálogo em memória.

Uma varredura só, feita ao escolher a pasta, que não abre nenhum documento:
lista os arquivos, lê os índices XML e liga um ao outro. O resultado vive
na memória enquanto a janela estiver aberta e é descartado ao fechar — é o
mesmo catálogo que serve à consulta e à contagem.

O vínculo entre registro e arquivo é feito pelo **caminho**, não só pelo
nome. Antes, três `documento.pdf` em pastas diferentes viravam um documento
só (os outros dois sumiam do catálogo e do total de páginas), e um PDF
citado em dois XML — reexportação de lote — entrava duas vezes, com as
páginas somadas em dobro.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from . import datas, nomes, xml_parser
from . import perfil as perfis
from .leitores import EXTENSOES_SUPORTADAS
from .texto import normalizar

EXTENSOES_XML = {".xml"}

ORIGEM_XML = "índice"
ORIGEM_NOME = "nome"

TIPO_OUTRO = "outro"
ROTULO_OUTRO = "Outro tipo de documento"

# Bases para "data do arquivo"
BASE_CRIACAO = "criacao"
BASE_MODIFICACAO = "modificacao"
BASE_INTERNA = "interna"
BASES_DATA = {
    BASE_CRIACAO: "criação do arquivo",
    BASE_MODIFICACAO: "modificação do arquivo",
    BASE_INTERNA: "data interna do PDF",
}

# Quantos valores olhar por campo ao decidir se ele é de data.
AMOSTRA_DATA = 200


@dataclass(eq=False)
class Documento:
    """Um documento do acervo: um registro de índice, um arquivo, ou os dois."""

    campos: dict[str, str] = field(default_factory=dict)
    nome_arquivo: str = ""
    caminho: Path | None = None
    origem: str = ORIGEM_NOME
    tipo: str = ""  # tipo reconhecido pelo padrão do nome do arquivo
    xml_origem: str = ""
    paginas_indice: int | None = None  # "Page count in document" do XML
    paginas_reais: int | None = None  # contadas abrindo o arquivo
    estado: str = ""  # vazio enquanto o arquivo não foi aberto
    erro: str = ""
    tamanho: int = 0
    data_criacao: datetime | None = None
    data_modificacao: datetime | None = None
    data_interna: datetime | None = None  # gravada dentro do PDF
    sha256: str = ""
    pdfa: str = ""
    vinculo_ambiguo: bool = False
    # Campos exatamente como vieram do XML, antes de completar pelo nome
    campos_xml: dict[str, str] = field(default_factory=dict, repr=False)
    _nome_norm: str | None = field(default=None, repr=False)
    _indice_norm: str | None = field(default=None, repr=False)

    # ------------------------------------------------------------ páginas
    @property
    def paginas(self) -> int | None:
        """A contagem real quando já se abriu o arquivo; senão, a do índice."""
        return self.paginas_reais if self.paginas_reais is not None else self.paginas_indice

    @property
    def divergente(self) -> bool:
        return (
            self.paginas_indice is not None
            and self.paginas_reais is not None
            and self.paginas_indice != self.paginas_reais
        )

    # ------------------------------------------------------------ arquivo
    @property
    def localizado(self) -> bool:
        return self.caminho is not None

    @property
    def extensao(self) -> str:
        return Path(self.nome_arquivo or (self.caminho.name if self.caminho else "")).suffix.lower()

    @property
    def lido(self) -> bool:
        return bool(self.estado)

    def data_arquivo(self, base: str = BASE_CRIACAO) -> datetime | None:
        if base == BASE_MODIFICACAO:
            return self.data_modificacao
        if base == BASE_INTERNA:
            return self.data_interna
        return self.data_criacao

    # ------------------------------------------------------------ índice
    def valor(self, campo: str) -> str:
        return self.campos.get(campo, "")

    def texto_indexado(self) -> str:
        """Todos os valores de índice juntos, para a busca por texto livre."""
        return " ".join(self.campos.values())

    def nome_normalizado(self) -> str:
        if self._nome_norm is None:
            self._nome_norm = normalizar(self.nome_arquivo)
        return self._nome_norm

    def indice_normalizado(self) -> str:
        if self._indice_norm is None:
            self._indice_norm = normalizar(self.texto_indexado())
        return self._indice_norm

    def titulo(self) -> str:
        for nome_campo, valor in self.campos.items():
            if normalizar(nome_campo) == "titulo" and valor.strip():
                return valor.strip()
        return ""


def _tipo_por_texto(texto: str) -> str:
    # "_" e "-" contam como espaço, senão "LEIS_2019" não seria palavra inteira
    limpo = re.sub(r"[_\-.]+", " ", normalizar(texto))
    for tipo in perfis.ativo().tipos:
        if tipo.pistas.search(limpo):
            return tipo.chave
    return ""


def classificar(documento: Documento, raiz: Path) -> str:
    """Enquadra o documento num dos tipos do perfil, ou em "outro".

    As pistas são tentadas da mais específica para a mais genérica: o
    padrão do nome do arquivo, depois o campo "Título" do índice, depois
    o nome das pastas entre o documento e o diretório escolhido — da mais
    próxima para a mais distante. Pastas acima do diretório escolhido não
    contam: "C:\\Usuários\\Despesas da casa\\..." não diz nada sobre o acervo.
    """
    chaves = {tipo.chave for tipo in perfis.ativo().tipos}
    if documento.tipo in chaves:
        return documento.tipo

    pelo_titulo = _tipo_por_texto(documento.titulo())
    if pelo_titulo:
        return pelo_titulo

    for origem in (documento.caminho, documento.xml_origem):
        if not origem:
            continue
        try:
            relativo = Path(origem).parent.relative_to(raiz)
        except ValueError:
            continue
        for pasta in reversed(relativo.parts):
            pela_pasta = _tipo_por_texto(pasta)
            if pela_pasta:
                return pela_pasta

    return TIPO_OUTRO


@dataclass
class Progresso:
    fase: str
    atual: int
    total: int
    mensagem: str = ""


@dataclass
class RegistroDuplicado:
    """Um registro de índice descartado por apontar um arquivo já catalogado."""

    nome_arquivo: str
    xml_descartado: str
    xml_mantido: str
    campos_diferentes: bool


@dataclass
class Catalogo:
    """O acervo de um diretório, carregado em memória."""

    raiz: Path
    incluir_subpastas: bool = True
    documentos: list[Documento] = field(default_factory=list)
    vocabulario: list[str] = field(default_factory=list)
    # Campos do vocabulário cujos valores são datas — descobertos olhando
    # o conteúdo, já que o nome do campo varia de acervo para acervo.
    campos_data: list[str] = field(default_factory=list)
    tipo_ativo: str = ""
    # Preenchido só em "outro tipo de documento": os índices que o usuário
    # escolheu buscar, que também definem quais documentos aparecem.
    indices_escolhidos: list[str] = field(default_factory=list)
    xmls_lidos: int = 0
    xmls_tolerantes: list[str] = field(default_factory=list)
    xmls_com_falha: list[tuple[str, str]] = field(default_factory=list)
    arquivos_encontrados: int = 0
    registros_duplicados: list[RegistroDuplicado] = field(default_factory=list)
    # Pastas e arquivos que o sistema operacional não deixou ler
    inacessiveis: list[tuple[str, str]] = field(default_factory=list)
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

    @property
    def sem_indice(self) -> int:
        return sum(1 for d in self.documentos if d.origem == ORIGEM_NOME)

    @property
    def vinculos_ambiguos(self) -> int:
        return sum(1 for d in self.documentos if d.vinculo_ambiguo)

    # Compatibilidade com o nome antigo
    @property
    def sem_pdf(self) -> int:
        return self.sem_arquivo


def _info_arquivo(caminho: Path) -> tuple[int, datetime | None, datetime | None]:
    """Tamanho, criação e modificação, numa única chamada ao sistema.

    No Windows `st_ctime` é de fato a criação (e o Python 3.12+ oferece
    `st_birthtime`); em outros sistemas, sem data de criação, usamos a
    modificação. Atenção: copiar o acervo para outro disco redefine a data
    de criação para o dia da cópia — para isso existe a data interna do PDF.
    """
    info = caminho.stat()
    bruto = getattr(info, "st_birthtime", None)
    if bruto is None:
        bruto = info.st_ctime if os.name == "nt" else info.st_mtime

    def converter(valor: float) -> datetime | None:
        try:
            return datetime.fromtimestamp(valor)
        except (OSError, OverflowError, ValueError):
            return None

    return info.st_size, converter(bruto), converter(info.st_mtime)


def _percorrer(raiz: Path, incluir_subpastas: bool, falhas: list[tuple[str, str]]) -> Iterator[Path]:
    def registrar(exc: OSError) -> None:
        falhas.append((str(exc.filename or raiz), exc.strerror or str(exc)))

    if not incluir_subpastas:
        try:
            with os.scandir(raiz) as entradas:
                for entrada in entradas:
                    try:
                        if entrada.is_file():
                            yield Path(entrada.path)
                    except OSError as exc:
                        registrar(exc)
        except OSError as exc:
            registrar(exc)
        return
    for pasta, _subpastas, arquivos in os.walk(raiz, onerror=registrar):
        for nome_arquivo in arquivos:
            yield Path(pasta) / nome_arquivo


def _partes_normalizadas(caminho: str | Path) -> list[str]:
    return [normalizar(p) for p in re.split(r"[\\/]+", str(caminho)) if p and not p.endswith(":")]


def _escolher_arquivo(
    candidatos: list[Path], xml_path: Path, local_lote: str, vinculados: dict[Path, Documento]
) -> tuple[Path, bool]:
    """Entre arquivos homônimos, o que mais provavelmente é o do registro.

    Preferência: o que ainda não foi vinculado; o que está na mesma pasta
    do XML; o que tem mais pastas em comum com o "Batch Location"; o mais
    próximo do XML na árvore. Devolve também se a escolha foi incerta —
    o que vai para o relatório de auditoria.
    """
    livres = [c for c in candidatos if c not in vinculados] or candidatos
    if len(livres) == 1:
        return livres[0], False

    mesma_pasta = [c for c in livres if c.parent == xml_path.parent]
    if len(mesma_pasta) == 1:
        return mesma_pasta[0], False

    partes_lote = set(_partes_normalizadas(local_lote)) if local_lote else set()
    partes_xml = _partes_normalizadas(xml_path.parent)

    def pontuacao(candidato: Path) -> tuple[int, int]:
        partes = _partes_normalizadas(candidato.parent)
        no_lote = sum(1 for p in partes if p in partes_lote)
        comum = 0
        for a, b in zip(partes, partes_xml):
            if a != b:
                break
            comum += 1
        return no_lote, comum

    ordenados = sorted(livres, key=pontuacao, reverse=True)
    melhor, segundo = pontuacao(ordenados[0]), pontuacao(ordenados[1])
    ambiguo = melhor == segundo or melhor[0] == 0
    return ordenados[0], ambiguo


def varrer(
    raiz: Path | str,
    incluir_subpastas: bool = True,
    progresso: Callable[[Progresso], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Catalogo:
    raiz = Path(raiz)
    if not raiz.is_dir():
        raise FileNotFoundError(f"Diretório não encontrado: {raiz}")

    catalogo = Catalogo(raiz=raiz, incluir_subpastas=incluir_subpastas)

    def parou() -> bool:
        if cancelado is not None and cancelado():
            catalogo.cancelado = True
            return True
        return False

    # --- passo 1: listar, sem abrir nada
    if progresso:
        progresso(Progresso("listando", 0, 0, "Listando arquivos..."))

    por_nome: dict[str, list[Path]] = {}
    todos: list[Path] = []
    xmls: list[Path] = []
    for i, caminho in enumerate(_percorrer(raiz, incluir_subpastas, catalogo.inacessiveis)):
        if parou():
            return catalogo
        sufixo = caminho.suffix.lower()
        if sufixo in EXTENSOES_SUPORTADAS:
            por_nome.setdefault(caminho.name.lower(), []).append(caminho)
            todos.append(caminho)
        elif sufixo in EXTENSOES_XML or (sufixo == "" and xml_parser.parece_indice(caminho)):
            xmls.append(caminho)
        if progresso and i % 250 == 0:
            progresso(Progresso("listando", i, 0, f"{len(todos)} arquivos, {len(xmls)} índices"))

    catalogo.arquivos_encontrados = len(todos)

    def novo_documento(caminho: Path | None, **dados) -> Documento:
        documento = Documento(caminho=caminho, **dados)
        if caminho is not None:
            try:
                documento.tamanho, documento.data_criacao, documento.data_modificacao = _info_arquivo(caminho)
            except OSError as exc:
                catalogo.inacessiveis.append((str(caminho), exc.strerror or str(exc)))
        return documento

    # --- passo 2: ler os índices e vincular
    if progresso:
        progresso(Progresso("lendo", 0, len(xmls), f"Lendo {len(xmls)} índice(s)..."))

    vocabulario: list[str] = []
    vinculados: dict[Path, Documento] = {}
    sem_arquivo_vistos: dict[tuple, Documento] = {}

    for i, xml_path in enumerate(xmls):
        if parou():
            return catalogo
        if progresso:
            progresso(Progresso("lendo", i, len(xmls), xml_path.name))
        try:
            registros, tolerante = xml_parser.ler_indice(xml_path)
        except Exception as exc:
            catalogo.xmls_com_falha.append((str(xml_path), str(exc)))
            continue
        catalogo.xmls_lidos += 1
        if tolerante:
            catalogo.xmls_tolerantes.append(str(xml_path))

        for registro in registros:
            nome_arquivo = registro.nome_arquivo
            candidatos = por_nome.get(nome_arquivo.lower(), []) if nome_arquivo else []
            caminho, ambiguo = (None, False)
            if candidatos:
                caminho, ambiguo = _escolher_arquivo(
                    candidatos, xml_path, registro.local_lote, vinculados
                )

            # Mesmo arquivo já catalogado por outro registro: é reexportação.
            # Fica o primeiro; o descarte vai para a auditoria.
            if caminho is not None and caminho in vinculados:
                mantido = vinculados[caminho]
                catalogo.registros_duplicados.append(
                    RegistroDuplicado(
                        nome_arquivo, str(xml_path), mantido.xml_origem,
                        campos_diferentes=registro.campos != mantido.campos_xml,
                    )
                )
                continue
            if caminho is None:
                chave = (nome_arquivo.lower(), tuple(sorted(registro.campos.items())))
                if chave in sem_arquivo_vistos:
                    catalogo.registros_duplicados.append(
                        RegistroDuplicado(nome_arquivo, str(xml_path),
                                          sem_arquivo_vistos[chave].xml_origem, False)
                    )
                    continue

            campos = dict(registro.campos)
            for nome_campo in campos:
                if nome_campo not in vocabulario:
                    vocabulario.append(nome_campo)

            tipo, do_nome = nomes.do_nome(nome_arquivo)
            do_caminho = nomes.do_caminho(registro.local_lote or str(caminho.parent if caminho else ""))
            originais = dict(campos)
            _completar(campos, do_nome, vocabulario)
            _completar(campos, do_caminho, vocabulario)

            documento = novo_documento(
                caminho,
                campos=campos,
                nome_arquivo=nome_arquivo or (caminho.name if caminho else ""),
                origem=ORIGEM_XML,
                tipo=tipo,
                xml_origem=str(xml_path),
                paginas_indice=registro.paginas,
                vinculo_ambiguo=ambiguo,
                campos_xml=originais,
            )
            catalogo.documentos.append(documento)
            if caminho is not None:
                vinculados[caminho] = documento
            else:
                sem_arquivo_vistos[(nome_arquivo.lower(), tuple(sorted(registro.campos.items())))] = documento

    # --- passo 3: arquivos que nenhum índice menciona
    for i, caminho in enumerate(todos):
        if caminho in vinculados:
            continue
        if i % 500 == 0 and parou():
            return catalogo
        tipo, do_nome = nomes.do_nome(caminho.name)
        campos: dict[str, str] = {}
        _completar(campos, do_nome, vocabulario)
        _completar(campos, nomes.do_caminho(str(caminho.parent)), vocabulario)
        catalogo.documentos.append(
            novo_documento(caminho, campos=campos, nome_arquivo=caminho.name, origem=ORIGEM_NOME, tipo=tipo)
        )

    catalogo.vocabulario = vocabulario
    catalogo.campos_data = detectar_campos_de_data(catalogo)
    if progresso:
        progresso(Progresso("concluido", 1, 1, "Concluído"))
    return catalogo


def detectar_campos_de_data(catalogo: Catalogo) -> list[str]:
    """Quais campos do vocabulário contêm datas, julgando pelos valores."""
    encontrados: list[str] = []
    for campo in catalogo.vocabulario:
        amostra: list[str] = []
        for documento in catalogo.documentos:
            valor = documento.valor(campo)
            if valor and valor.strip():
                amostra.append(valor)
            if len(amostra) >= AMOSTRA_DATA:
                break
        if datas.parece_campo_de_data(amostra, nome_campo=campo):
            encontrados.append(campo)
    return encontrados


@dataclass
class GrupoTipo:
    """Um dos tipos do perfil, com o que foi encontrado dele na pasta."""

    chave: str
    rotulo: str
    documentos: list[Documento] = field(default_factory=list)
    vocabulario: list[str] = field(default_factory=list)

    @property
    def total_documentos(self) -> int:
        return len(self.documentos)

    @property
    def total_paginas(self) -> int:
        return sum(d.paginas or 0 for d in self.documentos)


def _vocabulario_de(documentos: list[Documento], ordem: list[str]) -> list[str]:
    presentes = {c for d in documentos for c, v in d.campos.items() if v.strip()}
    # Mantém a ordem do vocabulário geral, para as colunas não dançarem
    return [c for c in ordem if c in presentes]


def agrupar_por_tipo(catalogo: Catalogo) -> tuple[list[GrupoTipo], int]:
    """Distribui o catálogo entre os tipos do perfil.

    Devolve sempre todos os grupos, mesmo vazios — a tela de escolha mostra
    todos e diz quantos documentos de cada um existem na pasta —, e a
    quantidade de documentos que não se encaixou em nenhum deles.
    """
    tipos = perfis.ativo().tipos
    grupos = {t.chave: GrupoTipo(chave=t.chave, rotulo=t.rotulo) for t in tipos}
    sem_tipo = 0
    for documento in catalogo.documentos:
        chave = classificar(documento, catalogo.raiz)
        if chave in grupos:
            grupos[chave].documentos.append(documento)
        else:
            sem_tipo += 1
    for grupo in grupos.values():
        grupo.vocabulario = _vocabulario_de(grupo.documentos, catalogo.vocabulario)
    return [grupos[t.chave] for t in tipos], sem_tipo


def contagem_por_indice(catalogo: Catalogo) -> dict[str, int]:
    """Em quantos documentos cada índice aparece preenchido."""
    contagem = {campo: 0 for campo in catalogo.vocabulario}
    for documento in catalogo.documentos:
        for campo, valor in documento.campos.items():
            if valor.strip() and campo in contagem:
                contagem[campo] += 1
    return contagem


def _recorte(catalogo: Catalogo, documentos: list[Documento], vocabulario: list[str]) -> Catalogo:
    recorte = Catalogo(
        raiz=catalogo.raiz,
        incluir_subpastas=catalogo.incluir_subpastas,
        documentos=list(documentos),
        vocabulario=list(vocabulario),
        xmls_lidos=catalogo.xmls_lidos,
        xmls_tolerantes=catalogo.xmls_tolerantes,
        xmls_com_falha=catalogo.xmls_com_falha,
        arquivos_encontrados=catalogo.arquivos_encontrados,
        registros_duplicados=catalogo.registros_duplicados,
        inacessiveis=catalogo.inacessiveis,
    )
    recorte.campos_data = [c for c in catalogo.campos_data if c in recorte.vocabulario]
    return recorte


def subcatalogo(catalogo: Catalogo, grupo: GrupoTipo) -> Catalogo:
    """O catálogo restrito a um dos tipos do perfil, com os índices dele."""
    recorte = _recorte(catalogo, grupo.documentos, grupo.vocabulario)
    recorte.tipo_ativo = grupo.rotulo
    return recorte


def subcatalogo_por_indices(catalogo: Catalogo, indices: list[str]) -> Catalogo:
    """O catálogo em "outro tipo de documento", com os índices escolhidos.

    Os índices escolhidos viram os campos de busca e as colunas, e definem
    quais documentos aparecem — os que têm ao menos um deles preenchido.
    """
    escolhidos = [c for c in catalogo.vocabulario if c in set(indices)]
    if escolhidos:
        documentos = [d for d in catalogo.documentos if any(d.valor(c).strip() for c in escolhidos)]
    else:
        # Pasta sem índice nenhum (só arquivos soltos): mostra tudo, e a
        # busca fica por conta do nome do arquivo e do conteúdo.
        documentos = list(catalogo.documentos)
    recorte = _recorte(catalogo, documentos, escolhidos)
    recorte.tipo_ativo = ROTULO_OUTRO
    recorte.indices_escolhidos = escolhidos
    return recorte


def _completar(campos: dict[str, str], extras: dict[str, str], vocabulario: list[str]) -> None:
    """Preenche apenas o que o índice deixou vazio, sem sobrescrever o XML."""
    for nome_campo, valor in extras.items():
        if campos.get(nome_campo, "").strip():
            continue
        campos[nome_campo] = valor
        if nome_campo not in vocabulario:
            vocabulario.append(nome_campo)

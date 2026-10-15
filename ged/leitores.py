"""Leitura dos arquivos do acervo: páginas, texto, miniatura e conferência.

Um leitor por formato, escolhido pela extensão:

    PDF  (.pdf, .pdfa)          pypdfium2 — o motor de PDF do Chrome
    TIFF, PNG, JPG              Pillow — TIFF multipágina conta quadros
    SVG                         biblioteca padrão — sempre uma página

As duas bibliotecas têm licença permissiva (BSD/Apache e HPND) e são
gratuitas para quem desenvolve e para quem usa, inclusive para distribuir o
executável. O PyMuPDF, usado antes, é AGPL.

Sem as bibliotecas o programa continua de pé: a busca por nome e por
índice não abre arquivo nenhum, e a leitura devolve o estado "sem leitor"
em vez de quebrar.

O PDFium não pode ser chamado de duas threads ao mesmo tempo, então toda
chamada a ele passa pela mesma trava.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .datas import interpretar_data_pdf

# (rótulo na tela, extensões). A ordem é a dos checkboxes da contagem.
FORMATOS: list[tuple[str, tuple[str, ...]]] = [
    ("PDF (.pdf)", (".pdf",)),
    ("PDF/A (.pdfa)", (".pdfa",)),
    ("TIFF", (".tif", ".tiff")),
    ("PNG", (".png",)),
    ("JPG / JPEG", (".jpg", ".jpeg")),
    ("SVG", (".svg",)),
]
EXTENSOES_PDF = frozenset({".pdf", ".pdfa"})
EXTENSOES_IMAGEM = frozenset({".tif", ".tiff", ".png", ".jpg", ".jpeg"})
EXTENSOES_SVG = frozenset({".svg"})
EXTENSOES_SUPORTADAS = EXTENSOES_PDF | EXTENSOES_IMAGEM | EXTENSOES_SVG
EXTENSOES_PADRAO = frozenset({".pdf", ".pdfa"})

# Estados de leitura de um arquivo
OK = "ok"
ERRO = "erro"
PROTEGIDO = "protegido por senha"
VAZIO = "sem páginas"
INACESSIVEL = "inacessível"
SEM_LEITOR = "sem leitor"

_TRAVA_PDFIUM = threading.RLock()
_modulos: dict[str, object | None] = {}


def _modulo(nome: str):
    """Importa sob demanda e lembra o resultado.

    Sob demanda porque a instalação automática pode acontecer depois que o
    programa abriu; se a importação falhou, ela é tentada de novo na
    próxima chamada a `recarregar()`.
    """
    if nome not in _modulos:
        try:
            _modulos[nome] = importlib.import_module(nome)
        except ImportError:
            _modulos[nome] = None
    return _modulos[nome]


def recarregar() -> None:
    """Esquece as importações que falharam — chamado após instalar pacotes."""
    importlib.invalidate_caches()
    for nome in [n for n, m in _modulos.items() if m is None]:
        del _modulos[nome]


def _pdfium():
    return _modulo("pypdfium2")


def _pil_image():
    pil = _modulo("PIL.Image")
    if pil is not None:
        # Digitalizações de plantas e mapas passam fácil dos 179 megapixels
        # em que o Pillow recusa a imagem como "bomba de descompressão". Os
        # arquivos são do próprio acervo, então o limite só atrapalha.
        pil.MAX_IMAGE_PIXELS = None
    return pil


def pdf_disponivel() -> bool:
    return _pdfium() is not None


def imagem_disponivel() -> bool:
    return _pil_image() is not None


def disponivel(extensao: str) -> bool:
    extensao = extensao.lower()
    if extensao in EXTENSOES_PDF:
        return pdf_disponivel()
    if extensao in EXTENSOES_IMAGEM:
        return imagem_disponivel()
    return extensao in EXTENSOES_SVG


@dataclass
class Leitura:
    """O que se apurou abrindo um arquivo."""

    paginas: int | None
    estado: str = OK
    erro: str = ""
    data_interna: datetime | None = None


def _mensagem_pdfium(exc: Exception) -> tuple[str, str]:
    texto = str(exc)
    if "password" in texto.lower():
        return PROTEGIDO, "PDF protegido por senha"
    if "data format" in texto.lower():
        return ERRO, "arquivo corrompido ou não é um PDF"
    # O PDFium recusa abrir um PDF sem nenhuma página, com o código de erro 0
    if "pdfium: success" in texto.lower():
        return VAZIO, "o PDF não tem nenhuma página"
    return ERRO, texto


def ler(caminho: Path | str, extensao: str | None = None, verificar_imagem: bool = False) -> Leitura:
    """Conta as páginas de um arquivo, sem renderizar nada.

    `verificar_imagem` decodifica a imagem por inteiro para confirmar que
    não está truncada — mais lento, por isso só na conferência aprofundada.
    """
    caminho = Path(caminho)
    extensao = (extensao or caminho.suffix).lower()
    try:
        if extensao in EXTENSOES_PDF:
            return _ler_pdf(caminho)
        if extensao in EXTENSOES_IMAGEM:
            return _ler_imagem(caminho, verificar_imagem)
        if extensao in EXTENSOES_SVG:
            return _ler_svg(caminho)
    except PermissionError as exc:
        return Leitura(None, INACESSIVEL, f"sem permissão de leitura ({exc.strerror or exc})")
    except FileNotFoundError:
        return Leitura(None, INACESSIVEL, "arquivo não encontrado (removido ou disco desconectado)")
    except OSError as exc:
        return Leitura(None, INACESSIVEL, str(exc))
    return Leitura(None, ERRO, f"extensão não suportada: {extensao}")


@contextmanager
def _documento_pdf(caminho: Path | str):
    """Abre o PDF a partir de um arquivo que nós mesmos abrimos e fechamos.

    Recebendo o caminho, o PDFium deixava o arquivo aberto quando recusava o
    documento — e no Windows um arquivo aberto não pode ser movido nem
    apagado enquanto o programa estiver aberto.
    """
    pdfium = _pdfium()
    with _TRAVA_PDFIUM, open(caminho, "rb") as fh:
        documento = pdfium.PdfDocument(fh)
        try:
            yield documento
        finally:
            documento.close()


def _ler_pdf(caminho: Path) -> Leitura:
    pdfium = _pdfium()
    if pdfium is None:
        return Leitura(None, SEM_LEITOR, "componente de leitura de PDF (pypdfium2) não instalado")
    try:
        with _documento_pdf(caminho) as documento:
            paginas = len(documento)
            try:
                data = interpretar_data_pdf(documento.get_metadata_value("CreationDate"))
            except Exception:
                data = None
    except pdfium.PdfiumError as exc:
        estado, mensagem = _mensagem_pdfium(exc)
        return Leitura(0 if estado == VAZIO else None, estado, mensagem)
    if paginas == 0:
        return Leitura(0, VAZIO, "o PDF não tem nenhuma página", data)
    return Leitura(paginas, OK, "", data)


def _ler_imagem(caminho: Path, verificar: bool) -> Leitura:
    image = _pil_image()
    if image is None:
        return Leitura(None, SEM_LEITOR, "componente de leitura de imagens (Pillow) não instalado")
    try:
        if verificar:
            with image.open(caminho) as img:
                img.verify()
        # n_frames lê só a estrutura: contar quadros não exige decodificar
        # a imagem, que é o que deixava TIFFs grandes lentos.
        with image.open(caminho) as img:
            paginas = int(getattr(img, "n_frames", 1) or 1)
    except image.UnidentifiedImageError:
        return Leitura(None, ERRO, "formato de imagem não reconhecido")
    except (OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, (PermissionError, FileNotFoundError)):
            raise
        return Leitura(None, ERRO, f"imagem danificada: {exc}")
    return Leitura(paginas, OK)


def _ler_svg(caminho: Path) -> Leitura:
    with caminho.open("rb") as fh:
        inicio = fh.read(65536)
    if b"<svg" not in inicio.lower():
        return Leitura(None, ERRO, "SVG inválido (tag <svg> não encontrada)")
    return Leitura(1, OK)


# ------------------------------------------------------------------ texto
def texto_pdf(caminho: Path | str) -> tuple[str, str]:
    """Texto de todas as páginas, e o erro (vazio se deu certo)."""
    pdfium = _pdfium()
    if pdfium is None:
        return "", "pypdfium2 não instalado"
    partes: list[str] = []
    try:
        with _documento_pdf(caminho) as documento:
            for indice in range(len(documento)):
                pagina = documento[indice]
                try:
                    texto = pagina.get_textpage()
                    try:
                        partes.append(texto.get_text_bounded())
                    finally:
                        texto.close()
                finally:
                    pagina.close()
    except Exception as exc:  # arquivo ilegível, ou página corrompida no meio dele
        return "\n".join(partes), str(exc)
    return "\n".join(partes), ""


# -------------------------------------------------------------- miniatura
def miniatura_ppm(caminho: Path | str, largura: int = 230) -> bytes | None:
    """Primeira página como imagem PPM, que o Tk mostra sem bibliotecas extras."""
    caminho = Path(caminho)
    extensao = caminho.suffix.lower()
    image = _pil_image()
    if image is None:
        return None
    try:
        if extensao in EXTENSOES_PDF:
            if _pdfium() is None:
                return None
            with _documento_pdf(caminho) as documento:
                if len(documento) == 0:
                    return None
                pagina = documento[0]
                try:
                    escala = largura / max(pagina.get_width(), 1)
                    figura = pagina.render(scale=escala).to_pil()
                finally:
                    pagina.close()
        elif extensao in EXTENSOES_IMAGEM:
            with image.open(caminho) as img:
                img.seek(0)
                figura = img.convert("RGB")
                figura.thumbnail((largura, largura * 2))
        else:
            return None
        saida = io.BytesIO()
        figura.convert("RGB").save(saida, format="PPM")
        return saida.getvalue()
    except Exception:
        return None


# ----------------------------------------------------------- conferência
# O XMP de um PDF/A declara a parte e o nível: pdfaid:part="2" e
# pdfaid:conformance="B", como atributo ou como elemento. A norma proíbe
# compactar esse fluxo de metadados, então ele pode ser lido direto dos
# bytes do arquivo, na mesma passada que calcula o hash.
_PDFA_PARTE = re.compile(rb"pdfaid:part\s*(?:=\s*[\"'](\d)[\"']|>\s*(\d)\s*<)")
_PDFA_NIVEL = re.compile(rb"pdfaid:conformance\s*(?:=\s*[\"']([A-Za-z])[\"']|>\s*([A-Za-z])\s*<)")
_BLOCO = 1024 * 1024
_SOBREPOSICAO = 256


@dataclass
class Conferencia:
    sha256: str = ""
    pdfa: str = ""  # "PDF/A-2B", ou vazio se não declarado
    erro: str = ""


def conferir(caminho: Path | str, procurar_pdfa: bool = True) -> Conferencia:
    """SHA-256 do arquivo e, para PDF, a conformidade PDF/A declarada.

    Lê o arquivo inteiro uma única vez, em blocos — não carrega na memória.
    """
    resumo = hashlib.sha256()
    parte = nivel = b""
    cauda = b""
    try:
        with open(caminho, "rb") as fh:
            while True:
                bloco = fh.read(_BLOCO)
                if not bloco:
                    break
                resumo.update(bloco)
                if procurar_pdfa and not (parte and nivel):
                    janela = cauda + bloco
                    if not parte:
                        m = _PDFA_PARTE.search(janela)
                        if m:
                            parte = m.group(1) or m.group(2)
                    if not nivel:
                        m = _PDFA_NIVEL.search(janela)
                        if m:
                            nivel = m.group(1) or m.group(2)
                    cauda = janela[-_SOBREPOSICAO:]
    except OSError as exc:
        return Conferencia(erro=str(exc))
    pdfa = f"PDF/A-{parte.decode()}{nivel.decode().upper()}" if parte else ""
    return Conferencia(sha256=resumo.hexdigest(), pdfa=pdfa)

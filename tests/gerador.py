"""Arquivos de exemplo para os testes, gerados na hora — sem dados reais.

O gerador de PDF é Python puro: os testes não dependem de nenhuma
biblioteca para *criar* os arquivos, só para lê-los.
"""
from __future__ import annotations

from pathlib import Path


def _escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_bytes(paginas: int = 1, texto: str = "", criacao: str = "", pdfa: str = "") -> bytes:
    """PDF válido com N páginas.

    texto    escrito em todas as páginas (Helvetica, Latin-1)
    criacao  data interna, ex. "20191129103000"
    pdfa     conformidade declarada no XMP, ex. "2B"
    """
    objetos: list[bytes] = []

    def adicionar(corpo: bytes) -> int:
        objetos.append(corpo)
        return len(objetos)

    id_catalogo = adicionar(b"")
    id_paginas = adicionar(b"")
    id_fonte = adicionar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    filhos = []
    for i in range(paginas):
        fluxo = f"BT /F1 12 Tf 72 720 Td ({_escapar(texto or f'Pagina {i + 1}')}) Tj ET".encode("latin-1")
        id_conteudo = adicionar(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream")
        id_pagina = adicionar(
            f"<< /Type /Page /Parent {id_paginas} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {id_fonte} 0 R >> >> /Contents {id_conteudo} 0 R >>".encode()
        )
        filhos.append(id_pagina)
    objetos[id_paginas - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in filhos)}] /Count {len(filhos)} >>".encode()
    )

    extra = ""
    if pdfa:
        xmp = (
            '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" '
            f'pdfaid:part="{pdfa[0]}" pdfaid:conformance="{pdfa[1:]}"/>'
            '</rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
        ).encode()
        id_meta = adicionar(b"<< /Type /Metadata /Subtype /XML /Length %d >>\nstream\n" % len(xmp) + xmp + b"\nendstream")
        extra = f" /Metadata {id_meta} 0 R"
    objetos[id_catalogo - 1] = f"<< /Type /Catalog /Pages {id_paginas} 0 R{extra} >>".encode()

    info = ""
    if criacao:
        id_info = adicionar(f"<< /CreationDate (D:{criacao}) /Producer (testes) >>".encode())
        info = f" /Info {id_info} 0 R"

    saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += f"{numero} 0 obj\n".encode() + corpo + b"\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for posicao in posicoes:
        saida += f"{posicao:010d} 00000 n \n".encode()
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root {id_catalogo} 0 R{info} >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(saida)


def gerar_pdf(caminho: Path, paginas: int = 1, **opcoes) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(pdf_bytes(paginas, **opcoes))
    return caminho


def indice_xml(registros: list[dict], encoding: str = "utf-8") -> bytes:
    """Índice no formato do Kodak Capture.

    Cada registro é um dict de campos de índice, mais as chaves especiais
    "_arquivo", "_paginas" e "_lote" para os campos de sistema.
    """
    def atributo(valor: str) -> str:
        return valor.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

    linhas = ['<?xml version="1.0" encoding="utf-8"?>', "<root>"]
    for registro in registros:
        linhas.append("  <document>")
        for nome, valor in registro.items():
            if nome.startswith("_"):
                continue
            linhas.append(f'    <field level="document" name="{atributo(nome)}" value="{atributo(str(valor))} "/>')
        sistema = {
            "Document File Name": registro.get("_arquivo", ""),
            "Page count in document": registro.get("_paginas", ""),
            "Batch Location": registro.get("_lote", ""),
        }
        for nome, valor in sistema.items():
            if valor != "":
                linhas.append(f'    <field level="system" name="{nome}" value="{atributo(str(valor))}"/>')
        linhas.append("  </document>")
    linhas.append("</root>")
    # Grava no encoding pedido, mas sempre declarando utf-8 — como o export real
    return "\n".join(linhas).encode(encoding)

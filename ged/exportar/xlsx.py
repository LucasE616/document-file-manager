"""Planilha .xlsx escrita só com a biblioteca padrão.

Um .xlsx é um zip de arquivos XML. Para o que os relatórios precisam —
várias abas, cabeçalho em negrito, primeira linha congelada, larguras de
coluna e números que o Excel soma — bastam algumas dezenas de linhas, e o
programa não ganha mais uma dependência para instalar.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PROIBIDOS_NO_NOME = re.compile(r"[\[\]:*?/\\]")
LIMITE_CELULA = 32767


@dataclass
class Planilha:
    nome: str
    linhas: list[list] = field(default_factory=list)
    negrito: set[int] = field(default_factory=lambda: {0})  # índices de linha
    congelar_linhas: int = 1
    larguras: list[int] | None = None  # em caracteres; None = automático


def _coluna(indice: int) -> str:
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _celula(referencia: str, valor, estilo: int) -> str:
    atributo_estilo = f' s="{estilo}"' if estilo else ""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, bool):
        valor = "sim" if valor else "não"
    if isinstance(valor, (int, float)):
        return f'<c r="{referencia}"{atributo_estilo}><v>{valor}</v></c>'
    if isinstance(valor, datetime):
        valor = valor.strftime("%d/%m/%Y %H:%M")
    elif isinstance(valor, date):
        valor = valor.strftime("%d/%m/%Y")
    texto = _CONTROLE.sub("", str(valor))[:LIMITE_CELULA]
    return (
        f'<c r="{referencia}" t="inlineStr"{atributo_estilo}>'
        f'<is><t xml:space="preserve">{escape(texto)}</t></is></c>'
    )


def _larguras(planilha: Planilha) -> list[int]:
    if planilha.larguras:
        return planilha.larguras
    maximos: list[int] = []
    for linha in planilha.linhas[:2000]:
        for i, valor in enumerate(linha):
            tamanho = len(str(valor)) if valor is not None else 0
            if i >= len(maximos):
                maximos.append(0)
            maximos[i] = max(maximos[i], tamanho)
    return [min(max(m + 2, 8), 70) for m in maximos]


def _folha(planilha: Planilha) -> str:
    partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if planilha.congelar_linhas:
        n = planilha.congelar_linhas
        partes.append(
            f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{n}" topLeftCell="A{n + 1}" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        )
    larguras = _larguras(planilha)
    if larguras:
        partes.append("<cols>" + "".join(
            f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(larguras)
        ) + "</cols>")
    partes.append("<sheetData>")
    for numero, linha in enumerate(planilha.linhas):
        estilo = 1 if numero in planilha.negrito else 0
        celulas = "".join(_celula(f"{_coluna(i)}{numero + 1}", v, estilo) for i, v in enumerate(linha))
        partes.append(f'<row r="{numero + 1}">{celulas}</row>')
    partes.append("</sheetData></worksheet>")
    return "".join(partes)


def _nome_valido(nome: str, usados: set[str]) -> str:
    base = _PROIBIDOS_NO_NOME.sub("_", nome).strip("'")[:31] or "Planilha"
    candidato, n = base, 2
    while candidato.lower() in usados:
        sufixo = f" ({n})"
        candidato = base[: 31 - len(sufixo)] + sufixo
        n += 1
    usados.add(candidato.lower())
    return candidato


def escrever_xlsx(destino: Path | str, planilhas: list[Planilha]) -> Path:
    destino = Path(destino)
    usados: set[str] = set()
    nomes = [_nome_valido(p.nome, usados) for p in planilhas]

    tipos = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(len(planilhas))
        )
        + "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    livro = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{escape(nome, {chr(34): "&quot;"})}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
            for i, nome in enumerate(nomes)
        )
        + "</sheets></workbook>"
    )
    livro_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(planilhas))
        )
        + f'<Relationship Id="rId{len(planilhas) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    estilos = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )

    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("[Content_Types].xml", tipos)
        pacote.writestr("_rels/.rels", rels)
        pacote.writestr("xl/workbook.xml", livro)
        pacote.writestr("xl/_rels/workbook.xml.rels", livro_rels)
        pacote.writestr("xl/styles.xml", estilos)
        for i, planilha in enumerate(planilhas):
            pacote.writestr(f"xl/worksheets/sheet{i + 1}.xml", _folha(planilha))
    return destino

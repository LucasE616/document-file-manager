"""Interpretação de datas escritas de qualquer jeito.

O acervo não tem um formato de data só. O mesmo arquivo de índice traz
`2019-11-29` na maioria dos registros e `01-11-2019` em outros, e o
usuário digita `29/11/2019`, que não é nenhum dos dois. Como os campos de
índice são descobertos em tempo de execução, a data é reconhecida pelo
formato do valor, não pelo nome do campo.

A consulta pode ser parcial: `2019` acha o ano inteiro, `11/2019` acha o
mês, `29/11/2019` acha o dia exato.

Cada formato só é tentado quando o valor tem exatamente a forma dele. O
`strptime` sozinho é permissivo demais: aceita um dígito em `%d` e `%m`,
e com isso `1012019` virava 09/01/1012 e `3112020` virava 31/01/2020 —
números de empenho e de processo eram tomados por datas.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime

from .texto import normalizar

ANO_MINIMO = 1900
ANO_MAXIMO = 2199

# (forma exigida, formato do strptime). O dia antes do mês vem primeiro por
# ser o uso brasileiro.
_FORMATOS_COM_SEPARADOR = (
    (re.compile(r"\d{4}-\d{1,2}-\d{1,2}"), "%Y-%m-%d"),
    (re.compile(r"\d{1,2}/\d{1,2}/\d{4}"), "%d/%m/%Y"),
    (re.compile(r"\d{1,2}-\d{1,2}-\d{4}"), "%d-%m-%Y"),
    (re.compile(r"\d{4}/\d{1,2}/\d{1,2}"), "%Y/%m/%d"),
    (re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}"), "%d.%m.%Y"),
)
# Oito dígitos sem separador: só valem quando o nome do campo indica data
# (ver parece_campo_de_data) ou quando o próprio usuário digita assim.
_FORMATOS_COMPACTOS = (
    (re.compile(r"\d{8}"), "%Y%m%d"),
    (re.compile(r"\d{8}"), "%d%m%Y"),
)

# Hora colada na data ("2019-11-29 00:00:00", "2019-11-29T10:30") é ignorada.
_HORA = re.compile(r"[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$")
_SEPARADOR = re.compile(r"[/\-.]")
_SO_DIGITOS = re.compile(r"^\d+$")
_DICA_DE_DATA = re.compile(r"\bdata\b|\bdt\b|vencimento|emissao|assinatura|publicacao|nascimento|pagto|pagamento")


def _ano_valido(valor: date) -> bool:
    return ANO_MINIMO <= valor.year <= ANO_MAXIMO


def interpretar(valor: str, aceitar_compacto: bool = True) -> date | None:
    """Converte um valor de índice em data, ou devolve None se não for uma."""
    valor = _HORA.sub("", (valor or "").strip())
    if not valor:
        return None
    formatos = _FORMATOS_COM_SEPARADOR + (_FORMATOS_COMPACTOS if aceitar_compacto else ())
    for forma, formato in formatos:
        if not forma.fullmatch(valor):
            continue
        try:
            convertida = datetime.strptime(valor, formato).date()
        except ValueError:
            continue
        if _ano_valido(convertida):
            return convertida
    return None


def interpretar_data_pdf(valor: str) -> datetime | None:
    """Data interna do PDF: 'D:20191129103000-03'00'' -> datetime.

    É a data gravada pelo software que gerou o arquivo. Ao contrário da
    data de criação no disco, ela não muda quando o acervo é copiado.
    """
    m = re.match(r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", (valor or "").strip())
    if not m:
        return None
    partes = [int(p) if p else padrao for p, padrao in zip(m.groups(), (0, 1, 1, 0, 0, 0))]
    try:
        convertida = datetime(*partes)
    except ValueError:
        return None
    return convertida if ANO_MINIMO <= convertida.year <= ANO_MAXIMO else None


@dataclass(frozen=True)
class DataParcial:
    """Uma data que o usuário digitou, possivelmente incompleta."""

    ano: int | None = None
    mes: int | None = None
    dia: int | None = None

    def casa(self, alvo: date) -> bool:
        if self.ano is not None and alvo.year != self.ano:
            return False
        if self.mes is not None and alvo.month != self.mes:
            return False
        if self.dia is not None and alvo.day != self.dia:
            return False
        return True

    def como_data(self, inicio: bool) -> date | None:
        """Vira uma data concreta, para servir de limite de período.

        `inicio=True` puxa para o começo do intervalo que a parcial
        descreve ("11/2019" → 01/11/2019); `inicio=False` puxa para o fim
        ("11/2019" → 30/11/2019). É o que faz "de 2019 até 2019" pegar o
        ano inteiro em vez de um dia só.
        """
        if self.ano is None:
            return None
        if self.mes is None:
            return date(self.ano, 1, 1) if inicio else date(self.ano, 12, 31)
        if self.dia is None:
            if inicio:
                return date(self.ano, self.mes, 1)
            return date(self.ano, self.mes, _ultimo_dia(self.ano, self.mes))
        try:
            return date(self.ano, self.mes, self.dia)
        except ValueError:
            return None


def _ultimo_dia(ano: int, mes: int) -> int:
    if mes == 12:
        return 31
    return (date(ano, mes + 1, 1) - date.resolution).day


def _ano_de_dois_digitos(valor: int) -> int:
    return 2000 + valor if valor <= 69 else 1900 + valor


def interpretar_consulta(texto: str) -> DataParcial | None:
    """Lê o que o usuário digitou como data, aceitando formas incompletas.

    Só trata como data o que tem separador ou é um ano de quatro dígitos —
    assim digitar "11" num campo continua sendo busca por texto, e não
    vira "novembro" sem que ninguém tenha pedido.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    if _SO_DIGITOS.match(texto):
        if len(texto) == 4 and ANO_MINIMO <= int(texto) <= ANO_MAXIMO:
            return DataParcial(ano=int(texto))
        if len(texto) == 8:
            completa = interpretar(texto)
            if completa:
                return DataParcial(completa.year, completa.month, completa.day)
        return None

    partes = [p for p in _SEPARADOR.split(texto) if p]
    if not partes or not all(_SO_DIGITOS.match(p) for p in partes):
        return None
    numeros = [int(p) for p in partes]

    if len(partes) == 3:
        completa = interpretar(texto, aceitar_compacto=False)
        if completa:
            return DataParcial(completa.year, completa.month, completa.day)
        # "29/11/19": ano com dois dígitos, só aceito na consulta
        if len(partes[2]) == 2:
            dia, mes, ano = numeros
            try:
                d = date(_ano_de_dois_digitos(ano), mes, dia)
            except ValueError:
                return None
            return DataParcial(d.year, d.month, d.day)
        return None

    if len(partes) == 2:
        primeiro, segundo = numeros
        if len(partes[0]) == 4:  # "2019-11"
            return DataParcial(ano=primeiro, mes=segundo) if 1 <= segundo <= 12 else None
        if len(partes[1]) == 4:  # "11/2019"
            return DataParcial(ano=segundo, mes=primeiro) if 1 <= primeiro <= 12 else None
        if 1 <= primeiro <= 31 and 1 <= segundo <= 12:  # "29/11"
            return DataParcial(mes=segundo, dia=primeiro)
        return None

    return None


def casa_como_data(consulta: str, valor: str) -> bool | None:
    """Compara consulta e valor como datas.

    Devolve None quando a comparação não se aplica — porque a consulta não
    parece data, ou porque o valor não é uma. Nesse caso quem chamou deve
    cair para a busca por trecho de texto.
    """
    parcial = interpretar_consulta(consulta)
    if parcial is None:
        return None
    alvo = interpretar(valor)
    if alvo is None:
        return None
    return parcial.casa(alvo)


def limite_periodo(texto: str, inicio: bool) -> date | None:
    """Interpreta o que foi digitado num campo 'de'/'até' de período."""
    parcial = interpretar_consulta(texto)
    if parcial is None:
        return None
    return parcial.como_data(inicio)


def periodo_valido(texto: str) -> bool:
    """Vazio ou interpretável — para avisar o usuário de um período digitado errado."""
    return not (texto or "").strip() or limite_periodo(texto, inicio=True) is not None


def parece_campo_de_data(valores: list[str], nome_campo: str = "", minimo: int = 3) -> bool:
    """Decide se um campo de índice é de data, olhando o que ele contém.

    Exige que a maioria (60%) dos valores preenchidos sejam datas. Valores
    de oito dígitos sem separador só contam quando o nome do campo indica
    data, porque é exatamente a forma de um número de empenho. Com menos
    de `minimo` valores a amostra é pequena demais para julgar pelo
    conteúdo: o campo só vira data se todos forem datas e o nome indicar.
    """
    preenchidos = [v for v in valores if v and v.strip()]
    if not preenchidos:
        return False
    dica = bool(_DICA_DE_DATA.search(normalizar(nome_campo)))
    datas = sum(1 for v in preenchidos if interpretar(v, aceitar_compacto=dica) is not None)
    if len(preenchidos) < minimo:
        return dica and datas == len(preenchidos)
    return datas >= max(1, math.ceil(len(preenchidos) * 0.6))


def formatar(valor: date | datetime | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def formatar_com_hora(valor: datetime | None) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else ""

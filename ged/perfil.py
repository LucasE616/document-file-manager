"""Perfil do acervo: os tipos documentais e os padrões de nome.

Antes isso estava escrito no código (TIPOS_PRINCIPAIS, _PISTAS_TIPO,
PADROES_NOME), apesar de a proposta ser "nenhum tipo de documento no
código". Agora é um dado: o perfil padrão abaixo atende o acervo de
Despesas, Licitações e Legislações, e um arquivo `ged_perfil.json` ao lado
do programa — ou indicado com `--perfil` — o substitui, sem alterar código.

`exemplos/ged_perfil.json` é uma cópia exata do perfil padrão, pronta para
ser editada.

Formato:
    tipos[].chave           identificador ("despesa")
    tipos[].rotulo          nome mostrado ao usuário ("Despesas")
    tipos[].pistas          expressão procurada no Título do índice e no nome
                            das pastas, já sem acento e em minúsculas
    tipos[].padroes_nome    expressões sobre o nome do arquivo; cada grupo
                            nomeado vira um campo de índice, e grupos que
                            começam com "_" só ancoram a expressão
    padroes_caminho         expressões sobre o caminho da pasta
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

NOME_ARQUIVO_PERFIL = "ged_perfil.json"

PERFIL_PADRAO: dict = {
    "tipos": [
        {
            "chave": "despesa",
            "rotulo": "Despesas",
            "pistas": "despesa",
            "padroes_nome": [
                r"^despesa[_-](?:(?P<Ano>\d{4})[_-])?(?P<Numero>\d+)-(?P<_data>\d{6})-(?P<_hora>\d{6})"
            ],
        },
        {
            "chave": "licitacao",
            "rotulo": "Licitações",
            "pistas": "licitac",
            "padroes_nome": [
                r"^licita[cç][aã]o[_-](?P<Numero>[\d./-]*?)-(?P<_data>\d{8})-(?P<_hora>\d{4})"
            ],
        },
        {
            "chave": "legislacao",
            "rotulo": "Legislações",
            # "lei" só como palavra inteira: "leilão" é modalidade de licitação
            "pistas": r"legislac|\bleis?\b|decreto|portaria|resoluc",
            "padroes_nome": [
                r"^(?P<Tipo>lei|lei[_-]complementar|decreto|portaria|resolu[cç][aã]o)[_-](?P<Numero>[\d.]+)[_-](?P<Ano>\d{4})"
            ],
        },
    ],
    "padroes_caminho": [
        # .../licitacao/2017/licitacao_098_76  -> Numero 098
        r"licita[cç][aã]o[_-](?P<Numero>\d+)[_-]",
        # .../DESPESAS_2019_121_NOV  ou  .../2019/...  -> Ano 2019
        r"(?:^|[_\-/\\])(?P<Ano>19\d{2}|20\d{2})(?:[_\-/\\]|$)",
    ],
}


class ErroPerfil(ValueError):
    """Perfil JSON com formato inválido — a mensagem diz onde."""


@dataclass
class TipoDocumental:
    chave: str
    rotulo: str
    pistas: re.Pattern[str]
    padroes_nome: list[re.Pattern[str]] = field(default_factory=list)


@dataclass
class Perfil:
    tipos: list[TipoDocumental]
    padroes_caminho: list[re.Pattern[str]]
    origem: str = "padrão"

    def rotulo(self, chave: str) -> str:
        for tipo in self.tipos:
            if tipo.chave == chave:
                return tipo.rotulo
        return chave


def _compilar(expressao: str, onde: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    try:
        return re.compile(expressao, flags)
    except re.error as exc:
        raise ErroPerfil(f"Expressão inválida em {onde}: {exc}") from exc


def montar(dados: dict, origem: str = "padrão") -> Perfil:
    if not isinstance(dados, dict) or not isinstance(dados.get("tipos"), list):
        raise ErroPerfil("O perfil precisa ter uma lista 'tipos'.")
    tipos: list[TipoDocumental] = []
    for i, bruto in enumerate(dados["tipos"]):
        onde = f"tipos[{i}]"
        if not isinstance(bruto, dict) or not bruto.get("chave") or not bruto.get("rotulo"):
            raise ErroPerfil(f"{onde} precisa de 'chave' e 'rotulo'.")
        if bruto["chave"] == "outro":
            raise ErroPerfil(f"{onde}: a chave 'outro' é reservada.")
        tipos.append(
            TipoDocumental(
                chave=str(bruto["chave"]),
                rotulo=str(bruto["rotulo"]),
                pistas=_compilar(str(bruto.get("pistas") or r"(?!)"), f"{onde}.pistas", 0),
                padroes_nome=[
                    _compilar(str(p), f"{onde}.padroes_nome[{j}]")
                    for j, p in enumerate(bruto.get("padroes_nome") or [])
                ],
            )
        )
    caminhos = [
        _compilar(str(p), f"padroes_caminho[{j}]")
        for j, p in enumerate(dados.get("padroes_caminho") or [])
    ]
    return Perfil(tipos=tipos, padroes_caminho=caminhos, origem=origem)


def carregar_arquivo(caminho: Path | str) -> Perfil:
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErroPerfil(f"Não foi possível ler o perfil {caminho}: {exc}") from exc
    return montar(dados, origem=str(caminho))


def pasta_do_programa() -> Path:
    """Pasta do .exe quando empacotado, ou a raiz do projeto quando em script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


_ativo: Perfil | None = None


def ativo() -> Perfil:
    """O perfil em uso: o `ged_perfil.json` ao lado do programa, se houver."""
    global _ativo
    if _ativo is None:
        local = pasta_do_programa() / NOME_ARQUIVO_PERFIL
        _ativo = carregar_arquivo(local) if local.is_file() else montar(PERFIL_PADRAO)
    return _ativo


def definir(perfil: Perfil | None) -> None:
    """Troca o perfil em uso (None volta a procurar o padrão)."""
    global _ativo
    _ativo = perfil

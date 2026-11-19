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
    tipos[].indices         opcional: os índices do tipo. Quando presente,
                            eles viram os campos de busca e as colunas, e
                            servem de pista para enquadrar documentos que
                            nenhuma outra pista enquadrou (ver catalogo.py)
    padroes_caminho         expressões sobre o caminho da pasta

Tipos criados pelo usuário (`criar_tipo`) entram neste mesmo formato e são
gravados no `ged_perfil.json` — é o único arquivo que o programa grava além
dos relatórios.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
import unicodedata
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
    # Índices do tipo, na ordem em que viram colunas. Vazio nos tipos que
    # usam todos os índices que os documentos trouxerem.
    indices: list[str] = field(default_factory=list)
    # Palavras-chave como o usuário digitou (só nos tipos criados por ele)
    palavras: list[str] = field(default_factory=list)


@dataclass
class Perfil:
    tipos: list[TipoDocumental]
    padroes_caminho: list[re.Pattern[str]]
    origem: str = "padrão"
    # O JSON de onde o perfil saiu, para gravá-lo de volta sem perder nada
    dados: dict = field(default_factory=dict, repr=False)

    def rotulo(self, chave: str) -> str:
        for tipo in self.tipos:
            if tipo.chave == chave:
                return tipo.rotulo
        return chave

    def tipo(self, chave: str) -> TipoDocumental | None:
        return next((t for t in self.tipos if t.chave == chave), None)

    @property
    def arquivo(self) -> Path | None:
        """O arquivo JSON do perfil, ou None quando é o perfil padrão embutido."""
        return None if self.origem == "padrão" else Path(self.origem)


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
        indices = bruto.get("indices") or []
        palavras = bruto.get("palavras") or []
        if not isinstance(indices, list) or not isinstance(palavras, list):
            raise ErroPerfil(f"{onde}: 'indices' e 'palavras' precisam ser listas.")
        tipos.append(
            TipoDocumental(
                chave=str(bruto["chave"]),
                rotulo=str(bruto["rotulo"]),
                pistas=_compilar(str(bruto.get("pistas") or r"(?!)"), f"{onde}.pistas", 0),
                padroes_nome=[
                    _compilar(str(p), f"{onde}.padroes_nome[{j}]")
                    for j, p in enumerate(bruto.get("padroes_nome") or [])
                ],
                indices=[str(i).strip() for i in indices if str(i).strip()],
                palavras=[str(p).strip() for p in palavras if str(p).strip()],
            )
        )
    caminhos = [
        _compilar(str(p), f"padroes_caminho[{j}]")
        for j, p in enumerate(dados.get("padroes_caminho") or [])
    ]
    return Perfil(tipos=tipos, padroes_caminho=caminhos, origem=origem, dados=copy.deepcopy(dados))


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


# ------------------------------------------------------------ tipos do usuário
CHAVE_RESERVADA = "outro"
ROTULO_RESERVADO = "Outro tipo de documento"


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def chave_para(rotulo: str, existentes: set[str] | list[str] = ()) -> str:
    """Identificador estável a partir do nome: "Contratos Aditivos" -> "contratos_aditivos"."""
    base = re.sub(r"[^a-z0-9]+", "_", _sem_acento(rotulo)).strip("_") or "tipo"
    if base == CHAVE_RESERVADA:
        base = "tipo_outro"
    chave, n = base, 2
    while chave in set(existentes):
        chave, n = f"{base}_{n}", n + 1
    return chave


def pistas_das_palavras(palavras: list[str]) -> str:
    """Converte palavras-chave digitadas pelo usuário na expressão de pistas.

    A comparação é feita sem acento e em minúsculas, e cada palavra precisa
    *começar* uma palavra do texto: "contrato" acha "CONTRATOS_2019", mas
    não "subcontratoria". Palavras de até três letras precisam aparecer
    inteiras — "lei" não pode achar "leilão".
    """
    partes = []
    for palavra in palavras:
        limpa = _sem_acento(palavra).strip()
        if not limpa:
            continue
        escapada = re.escape(limpa)
        partes.append(rf"\b{escapada}\b" if len(limpa) <= 3 else rf"\b{escapada}")
    return "|".join(partes)


def _separar(texto_ou_lista: str | list[str]) -> list[str]:
    itens = texto_ou_lista.split(",") if isinstance(texto_ou_lista, str) else texto_ou_lista
    vistos: list[str] = []
    for item in itens:
        item = str(item).strip()
        if item and _sem_acento(item) not in {_sem_acento(v) for v in vistos}:
            vistos.append(item)
    return vistos


def criar_tipo(perfil: Perfil, rotulo: str, indices: str | list[str],
               palavras: str | list[str] = ()) -> tuple[Perfil, str]:
    """Um perfil novo com o tipo acrescentado, e a chave dada ao tipo.

    O perfil recebido não é alterado. Exige um nome que ainda não exista e
    ao menos um índice: são os índices que fazem o tipo servir para buscar.
    """
    rotulo = " ".join((rotulo or "").split())
    if not rotulo:
        raise ErroPerfil("Dê um nome ao tipo documental.")
    nomes_usados = {_sem_acento(t.rotulo) for t in perfil.tipos} | {_sem_acento(ROTULO_RESERVADO)}
    if _sem_acento(rotulo) in nomes_usados:
        raise ErroPerfil(f'Já existe um tipo documental chamado "{rotulo}".')
    lista_indices = _separar(indices)
    if not lista_indices:
        raise ErroPerfil("Escolha ao menos um índice para o tipo documental.")
    lista_palavras = _separar(palavras)

    dados = copy.deepcopy(perfil.dados) if perfil.dados else copy.deepcopy(PERFIL_PADRAO)
    chave = chave_para(rotulo, {t.chave for t in perfil.tipos})
    novo: dict = {"chave": chave, "rotulo": rotulo, "indices": lista_indices}
    if lista_palavras:
        novo["palavras"] = lista_palavras
        novo["pistas"] = pistas_das_palavras(lista_palavras)
    dados.setdefault("tipos", []).append(novo)
    return montar(dados, origem=perfil.origem), chave


def excluir_tipo(perfil: Perfil, chave: str) -> Perfil:
    """Um perfil novo sem o tipo indicado."""
    dados = copy.deepcopy(perfil.dados) if perfil.dados else copy.deepcopy(PERFIL_PADRAO)
    restantes = [t for t in dados.get("tipos", []) if t.get("chave") != chave]
    if len(restantes) == len(dados.get("tipos", [])):
        raise ErroPerfil(f'Tipo documental "{chave}" não encontrado.')
    dados["tipos"] = restantes
    return montar(dados, origem=perfil.origem)


def arquivo_para_gravar(perfil: Perfil) -> Path:
    """Onde gravar: o próprio arquivo do perfil, ou o `ged_perfil.json` ao lado do programa."""
    return perfil.arquivo or (pasta_do_programa() / NOME_ARQUIVO_PERFIL)


def salvar(perfil: Perfil, caminho: Path | str | None = None) -> Perfil:
    """Grava o perfil em JSON e devolve o perfil com a origem atualizada.

    A gravação é atômica — um arquivo temporário renomeado por cima do
    antigo —, para que uma falha no meio não deixe um perfil pela metade,
    que impediria o programa de abrir.
    """
    destino = Path(caminho) if caminho else arquivo_para_gravar(perfil)
    dados = perfil.dados or copy.deepcopy(PERFIL_PADRAO)
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(prefix=".ged_perfil_", suffix=".tmp", dir=destino.parent)
        try:
            with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(texto)
            os.replace(temporario, destino)
        except BaseException:
            Path(temporario).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ErroPerfil(f"Não foi possível gravar o perfil em {destino}: {exc.strerror or exc}") from exc
    return montar(copy.deepcopy(dados), origem=str(destino))

"""Instalação automática dos componentes, só quando o programa roda como script.

O executável (.exe) já traz tudo embutido e não instala nada. Rodando como
script, os dois componentes que faltarem são instalados na primeira
execução, sem o usuário fazer nada:

    pypdfium2   ler PDFs: páginas, texto e miniatura      (BSD-3 / Apache-2.0)
    Pillow      ler TIFF, PNG e JPG; gerar miniaturas      (HPND)

Ambos gratuitos e de licença permissiva.

Ordem de tentativa:
1. a pasta `pacotes/` ao lado do programa, se existir — instalação sem
   internet, para máquinas isoladas (`python ferramentas/baixar_pacotes.py`
   prepara essa pasta);
2. o PyPI, se houver internet — verificada antes com um teste de conexão de
   poucos segundos, em vez de deixar o pip esperar. O contador antigo, sem
   internet, ficava até 10 minutos em "Verificando...";
3. o PyPI com `--user`, quando falta permissão na pasta do Python.

Depois de instalar, os caches de importação são invalidados e a pasta de
pacotes do usuário entra no caminho de busca — sem isso o pacote recém-
instalado podia continuar "não encontrado" até reabrir o programa.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import site
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TEMPO_LIMITE_INSTALACAO = 240  # segundos por tentativa
TEMPO_LIMITE_CONEXAO = 4


@dataclass(frozen=True)
class Pacote:
    modulo: str
    pip: str
    uso: str


PACOTES = (
    Pacote("pypdfium2", "pypdfium2", "ler PDFs (páginas, texto e miniatura)"),
    Pacote("PIL", "Pillow", "ler TIFF, PNG e JPG e gerar miniaturas"),
)


def empacotado() -> bool:
    return bool(getattr(sys, "frozen", False))


def pasta_pacotes() -> Path:
    from .perfil import pasta_do_programa

    return pasta_do_programa() / "pacotes"


def faltando() -> list[Pacote]:
    if empacotado():
        return []
    return [p for p in PACOTES if importlib.util.find_spec(p.modulo) is None]


def _em_ambiente_virtual() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _tem_internet() -> bool:
    try:
        with socket.create_connection(("pypi.org", 443), timeout=TEMPO_LIMITE_CONEXAO):
            return True
    except OSError:
        return False


def _executavel_python() -> str:
    """pythonw.exe (o .pyw) não tem console; para o pip, prefere o python.exe ao lado."""
    executavel = Path(sys.executable)
    if executavel.name.lower() == "pythonw.exe":
        console = executavel.with_name("python.exe")
        if console.exists():
            return str(console)
    return str(executavel)


def _pip(argumentos: list[str]) -> tuple[bool, str]:
    comando = [_executavel_python(), "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--quiet", *argumentos]
    criacao = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        processo = subprocess.run(comando, capture_output=True, text=True, timeout=TEMPO_LIMITE_INSTALACAO,
                                  creationflags=criacao)
    except subprocess.TimeoutExpired:
        return False, "tempo esgotado"
    except OSError as exc:
        return False, str(exc)
    saida = (processo.stderr or processo.stdout or "").strip()
    return processo.returncode == 0, saida.splitlines()[-1] if saida else ""


def _garantir_pip() -> bool:
    if importlib.util.find_spec("pip") is not None:
        return True
    try:
        subprocess.run([_executavel_python(), "-m", "ensurepip", "--default-pip"], capture_output=True,
                       timeout=TEMPO_LIMITE_INSTALACAO, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    importlib.invalidate_caches()
    return importlib.util.find_spec("pip") is not None


def _atualizar_caminhos() -> None:
    importlib.invalidate_caches()
    try:
        pasta_usuario = site.getusersitepackages()
    except Exception:
        return
    if os.path.isdir(pasta_usuario) and pasta_usuario not in sys.path:
        site.addsitedir(pasta_usuario)


def instalar(pacotes: list[Pacote], aviso: Callable[[str], None] | None = None) -> list[tuple[Pacote, str]]:
    """Instala os pacotes. Devolve os que falharam, com o motivo."""
    aviso = aviso or (lambda _t: None)
    if not pacotes:
        return []
    if not _garantir_pip():
        return [(p, "o instalador de pacotes (pip) não está disponível neste Python") for p in pacotes]

    local = pasta_pacotes()
    internet: bool | None = None
    falhas: list[tuple[Pacote, str]] = []
    for pacote in pacotes:
        motivo = ""
        instalado = False
        if local.is_dir():
            aviso(f"Instalando {pacote.pip} a partir da pasta 'pacotes'...")
            instalado, motivo = _pip(["--no-index", "--find-links", str(local), pacote.pip])
        if not instalado:
            if internet is None:
                aviso("Verificando a conexão com a internet...")
                internet = _tem_internet()
            if not internet:
                motivo = "sem conexão com a internet"
            else:
                aviso(f"Baixando e instalando {pacote.pip}...")
                instalado, motivo = _pip([pacote.pip])
                if not instalado and not _em_ambiente_virtual():
                    aviso(f"Tentando instalar {pacote.pip} só para este usuário...")
                    instalado, motivo = _pip(["--user", pacote.pip])
        _atualizar_caminhos()
        if not instalado or importlib.util.find_spec(pacote.modulo) is None:
            falhas.append((pacote, motivo or "instalado, mas não pôde ser carregado"))
    return falhas


def mensagem_de_falha(falhas: list[tuple[Pacote, str]]) -> str:
    linhas = ["Não foi possível preparar todos os componentes:", ""]
    for pacote, motivo in falhas:
        linhas.append(f"• {pacote.pip} — usado para {pacote.uso}: {motivo}")
    linhas += [
        "",
        "O programa continua funcionando: a busca por nome e pelos índices XML não depende deles.",
        "A instalação será tentada de novo na próxima vez que o programa abrir.",
        "",
        "Para não depender de internet, use a versão executável (.exe), que já traz tudo.",
    ]
    return "\n".join(linhas)


def garantir_no_terminal() -> None:
    """Versão de linha de comando: instala o que faltar e informa no terminal."""
    pacotes = faltando()
    if not pacotes:
        return
    print(f"Preparando componentes: {', '.join(p.pip for p in pacotes)}...", file=sys.stderr)
    falhas = instalar(pacotes, aviso=lambda t: print(f"  {t}", file=sys.stderr))
    if falhas:
        print(mensagem_de_falha(falhas), file=sys.stderr)
    from . import leitores

    leitores.recarregar()

"""Gera a versão executável para Windows — o usuário final não instala nada.

    python ferramentas/gerar_exe.py            pasta + .zip (recomendado)
    python ferramentas/gerar_exe.py --onefile  um único .exe

O script cria um ambiente isolado em `.build/`, instala ali o PyInstaller,
o pypdfium2 e o Pillow (todos gratuitos) e empacota o programa com o
Python, o Tkinter e as bibliotecas embutidos. Nada é instalado no Python
de quem roda o script.

A versão em pasta abre mais rápido e costuma ser menos barrada por
antivírus do que o .exe único, que precisa se descompactar a cada uso.

O resultado fica em `dist/`:
    dist/GED Offline/GED Offline.exe
    dist/GED-Offline-<versão>-windows.zip
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / ".build"
DIST = RAIZ / "dist"
NOME = "GED Offline"
PACOTES = ["pyinstaller>=6.10", "pypdfium2>=4.30", "Pillow>=10.4"]


def versao() -> str:
    for linha in (RAIZ / "ged" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if linha.startswith("__version__"):
            return linha.split("=", 1)[1].strip().strip('"\'')
    return "0"


def python_do_ambiente() -> Path:
    pasta = BUILD / "venv"
    executavel = pasta / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executavel.exists():
        print(f"Criando ambiente isolado em {pasta} ...")
        venv.EnvBuilder(with_pip=True, clear=True).create(pasta)
    return executavel


def rodar(comando: list[str]) -> None:
    print("> " + " ".join(str(c) for c in comando))
    subprocess.run([str(c) for c in comando], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--onefile", action="store_true", help="Gera um único .exe em vez de uma pasta.")
    args = parser.parse_args()

    python = python_do_ambiente()
    rodar([python, "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--upgrade", *PACOTES])

    comando = [
        python, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NOME,
        "--distpath", DIST, "--workpath", BUILD / "work", "--specpath", BUILD,
        "--collect-all", "pypdfium2", "--collect-all", "pypdfium2_raw",
        "--hidden-import", "PIL.Image", "--hidden-import", "PIL.TiffImagePlugin",
        "--onefile" if args.onefile else "--onedir",
        RAIZ / "main.py",
    ]
    rodar(comando)

    destino = DIST / (NOME if not args.onefile else "")
    destino.mkdir(parents=True, exist_ok=True)
    for extra in ("README.md", "LICENSE", "CHANGELOG.md"):
        if (RAIZ / extra).exists():
            shutil.copy2(RAIZ / extra, destino / extra)
    shutil.copy2(RAIZ / "exemplos" / "ged_perfil.json", destino / "ged_perfil.exemplo.json")

    if not args.onefile:
        pacote = DIST / f"GED-Offline-{versao()}-windows.zip"
        with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in sorted(destino.rglob("*")):
                zf.write(arquivo, Path(NOME) / arquivo.relative_to(destino))
        print(f"\nPronto: {destino / (NOME + '.exe')}\n        {pacote}")
    else:
        print(f"\nPronto: {DIST / (NOME + '.exe')}")


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        sys.exit("Use Python 3.10 ou mais novo.")
    main()

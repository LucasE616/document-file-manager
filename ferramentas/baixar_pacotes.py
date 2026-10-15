"""Prepara a pasta `pacotes/` para instalar o programa em máquinas sem internet.

    python ferramentas/baixar_pacotes.py

Rode numa máquina com internet e com a mesma versão do Python das máquinas
de destino. Depois copie a pasta do programa inteira, já com `pacotes/`:
na primeira execução o programa instala os componentes a partir dela,
sem acessar a internet.

Para máquinas sem internet, a alternativa mais simples continua sendo o
executável (ferramentas/gerar_exe.py), que já traz tudo.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PACOTES = ["pypdfium2", "Pillow"]


def main() -> None:
    destino = RAIZ / "pacotes"
    destino.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--dest", str(destino), *PACOTES],
        check=True,
    )
    print(f"\nPacotes prontos em {destino} (para Python {sys.version_info.major}.{sys.version_info.minor}).")


if __name__ == "__main__":
    main()

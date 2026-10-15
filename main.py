#!/usr/bin/env python3
"""GED Offline — consulta, contagem e auditoria do acervo digitalizado.

    python main.py                          abre a interface gráfica
    python main.py buscar <dir> [opções]    busca pela linha de comando
    python main.py contar <dir> [opções]    contagem e auditoria pela linha de comando
    python main.py testes                   testes automáticos
    python main.py --help                   todas as opções
"""
from __future__ import annotations

import sys

for _saida in (sys.stdout, sys.stderr):
    if _saida is not None and hasattr(_saida, "reconfigure"):
        try:
            _saida.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _abrir_interface() -> None:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print(
            "ERRO: o Tkinter não está disponível nesta instalação do Python.\n"
            "Use a versão executável (.exe), que já traz tudo, ou reinstale o Python\n"
            "marcando a opção 'tcl/tk and IDLE'.",
            file=sys.stderr,
        )
        sys.exit(1)
    from ged.gui import executar

    executar()


def main() -> None:
    argumentos = sys.argv[1:]
    if not argumentos:
        _abrir_interface()
        return
    from ged.cli import principal

    sys.exit(principal(argumentos))


if __name__ == "__main__":
    main()

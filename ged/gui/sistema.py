"""Abrir arquivos e pastas no sistema operacional."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import messagebox


def abrir_arquivo(caminho: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", caminho], check=False)
        else:
            subprocess.run(["xdg-open", caminho], check=False)
    except OSError as exc:
        messagebox.showerror("Erro ao abrir o arquivo", str(exc))


def comando_explorer(caminho: str) -> str:
    """Linha de comando que abre o Explorer com o arquivo selecionado.

    Precisa ser montada à mão. Passando uma lista de argumentos, o Python
    envolve o argumento inteiro em aspas quando o caminho tem espaço —
    "/select,C:\\Users\\...pdf" — e o Explorer, que só entende
    /select,"C:\\...pdf", ignora a instrução e abre Documentos.
    """
    return f'explorer /select,"{os.path.normpath(caminho)}"'


def abrir_pasta_do_arquivo(caminho: str) -> None:
    """Abre o gerenciador de arquivos já com o documento selecionado."""
    alvo = Path(os.path.normpath(caminho))
    if not alvo.exists():
        # Sem o arquivo, o /select do Explorer falha em silêncio e abre
        # Documentos — justamente o sintoma de "levou para o lugar errado".
        if alvo.parent.exists():
            messagebox.showinfo(
                "Arquivo não encontrado",
                f"O arquivo não está mais neste caminho:\n{alvo}\n\nVou abrir a pasta onde ele deveria estar.",
            )
            abrir_arquivo(str(alvo.parent))
        else:
            messagebox.showwarning(
                "Pasta não encontrada",
                f"A pasta deste documento não está acessível:\n{alvo.parent}\n\n"
                "Se o acervo está num HD externo ou na rede, confira se ele está conectado.",
            )
        return
    try:
        if sys.platform.startswith("win"):
            # O explorer devolve código 1 mesmo quando funciona, então o
            # resultado não é conferido de propósito.
            subprocess.run(comando_explorer(str(alvo)), check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(alvo)], check=False)
        else:
            subprocess.run(["xdg-open", str(alvo.parent)], check=False)
    except OSError as exc:
        messagebox.showerror("Erro ao abrir a pasta", str(exc))

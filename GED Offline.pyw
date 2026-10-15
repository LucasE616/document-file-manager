"""Abre o GED Offline sem janela de console (duplo clique no Windows).

Pelo .pyw não há console para mostrar erros; se a interface não conseguir
nem abrir, a mensagem aparece numa caixa de diálogo.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from main import _abrir_interface

    _abrir_interface()
except SystemExit:
    raise
except Exception:
    detalhe = traceback.format_exc()
    try:
        import tkinter
        from tkinter import messagebox

        raiz = tkinter.Tk()
        raiz.withdraw()
        messagebox.showerror("GED Offline", f"O programa não conseguiu abrir.\n\n{detalhe[-1500:]}")
        raiz.destroy()
    except Exception:
        pass
    raise

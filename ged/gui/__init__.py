"""Interface gráfica (Tkinter, da biblioteca padrão)."""


def executar() -> None:
    from .app import executar as _executar

    _executar()

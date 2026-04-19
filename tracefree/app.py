from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .ui import TraceFreeGUI


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    app = TraceFreeGUI(root)
    root.minsize(980, 620)
    app.root.mainloop()

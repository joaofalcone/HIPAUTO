#!/usr/bin/env python3
"""HIPAUTO Desktop V21 - interface direta, sem busca nem exportação."""

import tkinter as tk
from tkinter import ttk

import hipauto_desktop as base
import hipauto_desktop_v20 as v20


base.APP_VERSION = "21.0"


class HipautoDesktop(v20.HipautoDesktop):
    def _build_ui(self):
        super()._build_ui()
        toolbar = self.refresh_button.master
        for widget in toolbar.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.destroy()
            elif isinstance(widget, tk.Label) and widget.cget("text") == "Buscar:":
                widget.destroy()
            elif isinstance(widget, ttk.Button) and widget.cget("text") == "Exportar relatório":
                widget.destroy()
        self.refresh_button.pack_configure(padx=(0, 8))


if __name__ == "__main__":
    HipautoDesktop().mainloop()

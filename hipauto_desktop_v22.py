#!/usr/bin/env python3
"""HIPAUTO Desktop V22 - versão discreta no rodapé e link permanente."""

import tkinter as tk

import hipauto_desktop as base
import hipauto_desktop_v21 as v21


base.APP_VERSION = "22.0"


class HipautoDesktop(v21.HipautoDesktop):
    def _build_ui(self):
        super()._build_ui()

        # A versão deixa o cabeçalho e permanece somente no rodapé.
        for widget in self.winfo_children()[0].winfo_children():
            if isinstance(widget, tk.Frame):
                for label in widget.winfo_children():
                    if isinstance(label, tk.Label) and str(label.cget("text")).startswith("Aplicativo local"):
                        label.configure(text="Aplicativo local")

        footer = self.test_button.master
        hint = next((item for item in footer.winfo_children()
                     if isinstance(item, tk.Label) and str(item.cget("text")).startswith("Duplo clique")), None)
        version = tk.Label(footer, text=" v22.0 ", bg="#dfe7ec", fg="#41515c",
                           font=("Segoe UI Semibold", 8), padx=5, pady=3)
        if hint is not None:
            version.pack(side="left", before=hint, padx=(0, 10))
        else:
            version.pack(side="left")


if __name__ == "__main__":
    HipautoDesktop().mainloop()

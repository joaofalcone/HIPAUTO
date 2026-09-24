#!/usr/bin/env python3
"""HIPAUTO Desktop V20 - ajustes de clareza e empacotamento validado."""

import time
import tkinter as tk
from tkinter import ttk

import hipauto_desktop as v19


v19.APP_VERSION = "20.0"


class HipautoDesktop(v19.HipautoDesktop):
    def _build_ui(self):
        super()._build_ui()
        # A busca precisa de um rótulo visível; placeholder não é acessível e
        # desaparece durante a digitação. Inserimos o rótulo junto ao campo criado.
        toolbar = self.refresh_button.master
        search = next(widget for widget in toolbar.winfo_children() if isinstance(widget, ttk.Entry))
        label = tk.Label(toolbar, text="Buscar:", bg="#f4f6f8", fg="#41515c",
                         font=("Segoe UI Semibold", 9))
        label.pack_forget()
        label.pack(side="left", before=search, padx=(0, 8))

    def test_all(self):
        if not self.devices:
            return super().test_all()
        self.status_var.set("Testando todos os periféricos…")
        for device in self.devices:
            self.results[device["id"]] = {"status": "testing", "detail": "Teste em andamento"}
        self.populate_table()

        def task():
            results = {}
            for device in self.devices:
                try:
                    results[device["id"]] = v19.engine.test_device(device)
                except Exception as exc:
                    results[device["id"]] = {"status": "error", "detail": str(exc)}
            return results

        def done(result, error):
            self.finish_background()
            if error:
                for device in self.devices:
                    self.results[device["id"]] = {"status": "error", "detail": str(error)}
                self.populate_table()
                v19.messagebox.showerror("Falha nos testes", str(error), parent=self)
                return
            self.results.update(result)
            self.populate_table()
            ok_count = sum(item.get("status") == "ok" for item in result.values())
            self.status_var.set(f"Testes concluídos: {ok_count} de {len(result)} em estado OK")

        self.run_background(task, done)


if __name__ == "__main__":
    HipautoDesktop().mainloop()

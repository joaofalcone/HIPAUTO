#!/usr/bin/env python3
"""HIPAUTO Desktop - interface local nativa para o diagnóstico do PDV."""

from __future__ import annotations

import json
import platform
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import hipauto_v18 as engine

APP_VERSION = "19.0"
CATEGORIES = {"pinpad": "Pinpad", "scanner": "Scanner", "scale": "Balança",
              "printer": "Impressora", "keyboard": "Teclado", "biometric": "Biometria",
              "monitor": "Monitor", "unknown": "Outro"}
STATUS_LABELS = {"ok": "OK", "detected": "Detectado", "warning": "Atenção",
                 "error": "Falha", "testing": "Testando"}


class HipautoDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"HIPAUTO {APP_VERSION} · Diagnóstico do PDV")
        self.geometry("1180x720")
        self.minsize(900, 560)
        self.configure(bg="#f4f6f8")
        self.devices, self.results, self.busy = [], {}, False
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Preparando diagnóstico local…")
        self.summary_var = tk.StringVar(value="Nenhum periférico carregado")
        self._configure_style()
        self._build_ui()
        self.after(150, self.refresh_devices)

    def _configure_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("Treeview", rowheight=38, font=("Segoe UI", 10), background="#fff",
                        fieldbackground="#fff", borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), padding=8,
                        background="#e8edf2", foreground="#24313d")
        style.map("Treeview", background=[("selected", "#d9eaf7")], foreground=[("selected", "#17232d")])
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(14, 9),
                        background="#176b87", foreground="#fff")
        style.map("Primary.TButton", background=[("active", "#12566d"), ("disabled", "#9aadb5")])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 9))

    def _build_ui(self):
        header = tk.Frame(self, bg="#173042", padx=24, pady=18); header.pack(fill="x")
        tk.Label(header, text="H", width=3, bg="#26a69a", fg="white",
                 font=("Segoe UI Semibold", 18)).pack(side="left", padx=(0, 14))
        title = tk.Frame(header, bg="#173042"); title.pack(side="left")
        tk.Label(title, text="Diagnóstico do PDV", bg="#173042", fg="white",
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(title, text=f"Aplicativo local · HIPAUTO {APP_VERSION}", bg="#173042",
                 fg="#b9c9d3", font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(header, text="● LOCAL", bg="#173042", fg="#72d5b3",
                 font=("Segoe UI Semibold", 10)).pack(side="right")

        toolbar = tk.Frame(self, bg="#f4f6f8", padx=24, pady=16); toolbar.pack(fill="x")
        ttk.Entry(toolbar, textvariable=self.search_var, font=("Segoe UI", 10), width=38).pack(side="left")
        self.search_var.trace_add("write", lambda *_: self.populate_table())
        self.refresh_button = ttk.Button(toolbar, text="Atualizar", style="Secondary.TButton",
                                         command=self.refresh_devices)
        self.refresh_button.pack(side="left", padx=8)
        self.test_all_button = ttk.Button(toolbar, text="Testar todos", style="Primary.TButton",
                                          command=self.test_all)
        self.test_all_button.pack(side="left")
        ttk.Button(toolbar, text="Exportar relatório", style="Secondary.TButton",
                   command=self.export_report).pack(side="right")

        summary = tk.Frame(self, bg="#fff", padx=24, pady=12, highlightthickness=1,
                           highlightbackground="#dde3e8"); summary.pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(summary, textvariable=self.summary_var, bg="#fff", fg="#24313d",
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Label(summary, textvariable=self.status_var, bg="#fff", fg="#647580",
                 font=("Segoe UI", 9)).pack(side="right")

        content = tk.Frame(self, bg="#f4f6f8", padx=24); content.pack(fill="both", expand=True)
        columns = ("type", "name", "connection", "port", "status", "detail")
        self.tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="browse")
        for key, label, width in (("type", "Tipo", 110), ("name", "Equipamento", 240),
                                  ("connection", "Conexão", 90), ("port", "Porta", 130),
                                  ("status", "Estado", 100), ("detail", "Detalhes", 390)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=70, stretch=key in {"name", "detail"})
        self.tree.tag_configure("ok", foreground="#14785f")
        self.tree.tag_configure("error", foreground="#b83b3b")
        self.tree.tag_configure("warning", foreground="#a26400")
        self.tree.bind("<Double-1>", lambda _event: self.test_selected())
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")

        footer = tk.Frame(self, bg="#f4f6f8", padx=24, pady=14); footer.pack(fill="x")
        tk.Label(footer, text="Duplo clique em um equipamento para testar a comunicação.",
                 bg="#f4f6f8", fg="#647580", font=("Segoe UI", 9)).pack(side="left")
        self.test_button = ttk.Button(footer, text="Testar selecionado", style="Primary.TButton",
                                      command=self.test_selected)
        self.test_button.pack(side="right")

    def run_background(self, task, done):
        if self.busy: return
        self.busy = True
        for button in (self.refresh_button, self.test_all_button, self.test_button): button.state(["disabled"])
        def worker():
            try:
                result, error = task(), None
            except Exception as exc:
                result, error = None, exc
            self.after(0, lambda: done(result, error))
        threading.Thread(target=worker, daemon=True).start()

    def finish_background(self):
        self.busy = False
        for button in (self.refresh_button, self.test_all_button, self.test_button): button.state(["!disabled"])

    def refresh_devices(self):
        self.status_var.set("Procurando periféricos conectados…")
        def done(result, error):
            self.finish_background()
            if error:
                self.status_var.set("Não foi possível atualizar")
                messagebox.showerror("Falha no diagnóstico", str(error), parent=self); return
            self.devices = result
            known = {device["id"] for device in self.devices}
            self.results = {key: value for key, value in self.results.items() if key in known}
            self.populate_table(); self.status_var.set(time.strftime("Atualizado às %H:%M:%S"))
        self.run_background(engine.discover, done)

    def selected_device(self):
        selected = self.tree.selection()
        return next((item for item in self.devices if selected and item.get("id") == selected[0]), None)

    def test_selected(self):
        device = self.selected_device()
        if not device:
            messagebox.showinfo("Selecione um equipamento", "Escolha um item da lista para testar.", parent=self); return
        self.status_var.set(f"Testando {device.get('name', 'equipamento')}…")
        self.results[device["id"]] = {"status": "testing", "detail": "Teste em andamento"}
        self.populate_table(device["id"])
        def done(result, error):
            self.finish_background()
            self.results[device["id"]] = ({"status": "error", "detail": str(error)} if error else result)
            self.populate_table(device["id"])
            tested = self.results[device["id"]]
            self.status_var.set(f"Teste concluído: {STATUS_LABELS.get(tested.get('status'), 'Concluído')}")
            messagebox.showinfo("Resultado do teste", tested.get("detail", "Teste concluído"), parent=self)
        self.run_background(lambda: engine.test_device(device), done)

    def test_all(self):
        if not self.devices:
            messagebox.showinfo("Nenhum equipamento", "Atualize o inventário antes de iniciar os testes.", parent=self); return
        self.status_var.set("Testando todos os periféricos…")
        def task():
            results = {}
            for device in self.devices:
                try: results[device["id"]] = engine.test_device(device)
                except Exception as exc: results[device["id"]] = {"status": "error", "detail": str(exc)}
            return results
        def done(result, error):
            self.finish_background()
            if error: messagebox.showerror("Falha nos testes", str(error), parent=self); return
            self.results.update(result); self.populate_table()
            ok_count = sum(item.get("status") == "ok" for item in result.values())
            self.status_var.set(f"Testes concluídos: {ok_count} de {len(result)} em estado OK")
        self.run_background(task, done)

    def populate_table(self, keep_selection=None):
        current = keep_selection or (self.tree.selection()[0] if self.tree.selection() else None)
        for item in self.tree.get_children(): self.tree.delete(item)
        query = self.search_var.get().strip().casefold()
        for device in self.devices:
            result = self.results.get(device["id"], {})
            searchable = " ".join(str(value or "") for value in (device.get("category"), device.get("name"),
                                                                   device.get("connection"), device.get("port")))
            if query and query not in searchable.casefold(): continue
            status = result.get("status", device.get("status", "detected"))
            detail = result.get("detail", device.get("detail", "Aguardando teste"))
            if result.get("weight"): detail = f"{detail} · {result['weight']}"
            self.tree.insert("", "end", iid=device["id"], values=(
                CATEGORIES.get(device.get("category"), "Outro"), device.get("name") or "Equipamento sem nome",
                device.get("connection") or "—", device.get("port") or device.get("path") or "—",
                STATUS_LABELS.get(status, str(status).title()), detail), tags=(status,))
        tested = len(self.results); ok_count = sum(item.get("status") == "ok" for item in self.results.values())
        self.summary_var.set(f"{len(self.devices)} periférico(s) · {tested} testado(s) · {ok_count} OK")
        if current and self.tree.exists(current): self.tree.selection_set(current); self.tree.see(current)

    def export_report(self):
        if not self.devices:
            messagebox.showinfo("Sem dados", "Atualize o inventário antes de exportar.", parent=self); return
        filename = filedialog.asksaveasfilename(parent=self, title="Exportar relatório",
                    initialfile=time.strftime("hipauto-relatorio-%Y%m%d-%H%M%S.json"), defaultextension=".json",
                    filetypes=[("Relatório JSON", "*.json")])
        if not filename: return
        payload = {"schemaVersion": 7, "appVersion": APP_VERSION,
                   "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "environment": {"system": platform.system(), "release": platform.release(), "hostname": platform.node()},
                   "devices": [dict(device, testResult=self.results.get(device["id"])) for device in self.devices]}
        try:
            Path(filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status_var.set(f"Relatório salvo em {filename}")
        except OSError as exc: messagebox.showerror("Falha ao exportar", str(exc), parent=self)


if __name__ == "__main__":
    HipautoDesktop().mainloop()

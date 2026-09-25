"""Interface desktop (Tk) do HIPAUTO: cards por periférico, resumo e detalhes."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import __version__, checks, discovery, environment
from .icons import draw_icon, rounded_rect

BG = "#f3f6f9"
SURFACE = "#ffffff"
STRIPE = "#f5f8fa"
LINE = "#dce5eb"
INK = "#182b3a"
MUTED = "#5f7482"
HEADER = "#123044"
BRAND = "#087f8c"
GREEN = "#18a875"
GREEN_GLOW = "#63e6b8"
GREEN_SOFT = "#dff8ed"
RED = "#d94b55"
RED_SOFT = "#fdeced"
AMBER = "#b86e00"
AMBER_SOFT = "#fff4e0"
NEUTRAL_SOFT = "#edf2f5"

CATEGORIES = {"pinpad": "Pinpad", "scanner": "Leitor de código", "scale": "Balança",
              "printer": "Impressora", "keyboard": "Teclado", "biometric": "Biometria",
              "touchscreen": "Tela touch", "monitor": "Monitor", "unknown": "Outro"}
STATUS = {"detected": ("Conectado", GREEN), "ok": ("OK", GREEN), "warning": ("Atenção", AMBER),
          "error": ("Falha", RED), "testing": ("Testando…", BRAND)}
ACTIVE = {"ok", "detected"}
CARD_HEIGHT = 128
CARD_MIN_WIDTH = 250
VISIBLE_CARD_ROWS = 2


def pick_font(root: tk.Misc) -> str:
    families = set(tkfont.families(root))
    return next((name for name in ("Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Segoe UI")
                 if name in families), "TkDefaultFont")


def current_status(device: dict[str, Any], result: dict[str, Any] | None) -> str:
    return (result or {}).get("status") or device.get("status") or "detected"


def status_label(status: str) -> str:
    return STATUS.get(status, (str(status).title(), MUTED))[0]


def port_text(device: dict[str, Any]) -> str:
    return (device.get("port") or device.get("port_name") or device.get("queue")
            or device.get("path") or "Sem porta")


def detail_rows(device: dict[str, Any], result: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Label/value pairs shown in the details window; empty values are omitted."""
    merged = dict(device)
    merged.update(result or {})
    hom = merged.get("homologation") or {}
    conf = merged.get("confidence") or {}
    status = current_status(device, result)
    homologation = hom.get("label") if isinstance(hom, dict) else hom
    if isinstance(hom, dict) and hom.get("model"):
        homologation = f"{homologation} · {hom.get('manufacturer')} {hom.get('model')}"
        if hom.get("notes"):
            homologation += f" ({hom['notes']})"
    ports = merged.get("port_details") or {}
    serial_config = ""
    if ports.get("baudrate"):
        serial_config = (f"{ports.get('baudrate')} bps · {ports.get('data_bits') or 8}"
                         f"{ports.get('parity') or 'N'}{ports.get('stop_bits') or 1}")
    rows = [
        ("Tipo", CATEGORIES.get(merged.get("category"), "Outro")),
        ("Equipamento", merged.get("name")),
        ("Fabricante", merged.get("manufacturer")),
        ("Conexão", merged.get("connection")),
        ("Porta", port_text(device)),
        ("Porta recomendada", merged.get("recommended_port")
         if merged.get("recommended_port") != device.get("port") else None),
        ("Configuração serial", serial_config),
        ("Fila CUPS", merged.get("queue")),
        ("Estado", status_label(status)),
        ("Resultado", merged.get("detail")),
        ("Peso", merged.get("weight")),
        ("Protocolo", merged.get("scale_protocol")),
        ("Resposta (hex)", merged.get("hex")),
        ("Testado às", merged.get("tested_at")),
        ("Driver", merged.get("driver")),
        ("VID / PID", " / ".join(filter(None, [merged.get("vendor_id"), merged.get("product_id")]))),
        ("Número de série", merged.get("serial_number")),
        ("Firmware", merged.get("firmware")),
        ("Homologação", homologation),
        ("Confiança", " · ".join(filter(None, [conf.get("label"), conf.get("reason")]))
         if isinstance(conf, dict) else conf),
        ("Evidências", "\n".join(merged.get("evidence") or [])),
    ]
    return [(label, str(value)) for label, value in rows if value not in (None, "", [])]


class ScrollFrame(tk.Frame):
    """Vertical scroll container whose scrollbar appears only when needed."""

    def __init__(self, master: tk.Misc, bg: str, fixed_height: bool = False, **kwargs):
        super().__init__(master, bg=bg, **kwargs)
        self.fixed_height = fixed_height
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _e: self._sync())
        self.canvas.bind("<Configure>", self._resize)
        for widget in (self.canvas, self.inner):
            widget.bind("<Enter>", lambda _e: self._wheel(True), add="+")
            widget.bind("<Leave>", lambda _e: self._wheel(False), add="+")

    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync()

    def _sync(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        configured = int(float(self.canvas.cget("height") or 0))
        visible = configured if self.fixed_height else self.canvas.winfo_height()
        needed = self.inner.winfo_reqheight() > visible + 4 > 5
        if needed and not self.scrollbar.winfo_ismapped():
            self.scrollbar.pack(side="right", fill="y")
        elif not needed and self.scrollbar.winfo_ismapped():
            self.scrollbar.pack_forget()
            self.canvas.yview_moveto(0)

    def _wheel(self, active: bool) -> None:
        sequences = ("<MouseWheel>", "<Button-4>", "<Button-5>")
        for sequence in sequences:
            if active:
                self.canvas.bind_all(sequence, self._on_wheel)
            else:
                self.canvas.unbind_all(sequence)

    def _on_wheel(self, event: tk.Event) -> None:
        if not self.scrollbar.winfo_ismapped():
            return
        step = -1 if getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(step, "units")


class DeviceCard:
    """One clickable, keyboard-focusable card drawn on a Canvas."""

    def __init__(self, app: "HipautoDesktop", parent: tk.Misc, device: dict[str, Any]):
        self.app, self.device, self.result = app, device, None
        self.shape: int | None = None
        self.canvas = tk.Canvas(parent, height=CARD_HEIGHT, bg=BG, highlightthickness=0,
                                cursor="hand2", takefocus=1)
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        for sequence in ("<Button-1>", "<Return>", "<KP_Enter>", "<space>"):
            self.canvas.bind(sequence, lambda _e: self.app.open_details(self.device["id"]))
        self.canvas.bind("<FocusIn>", lambda _e: self.draw())
        self.canvas.bind("<FocusOut>", lambda _e: self.draw())

    @property
    def status(self) -> str:
        return current_status(self.device, self.result)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE

    def update(self, device: dict[str, Any], result: dict[str, Any] | None) -> None:
        self.device, self.result = device, result
        self.draw()

    def draw(self) -> None:
        canvas, fonts = self.canvas, self.app.fonts
        canvas.delete("all")
        width = max(canvas.winfo_width(), CARD_MIN_WIDTH) if canvas.winfo_width() > 1 else CARD_MIN_WIDTH
        status = self.status
        label, color = STATUS.get(status, (status_label(status), MUTED))
        focused = self.app.focus_get() is canvas
        border = BRAND if focused else (color if status != "detected" else GREEN)
        if status == "testing" and not focused:
            border = LINE
        soft = {"ok": GREEN_SOFT, "detected": GREEN_SOFT, "error": RED_SOFT,
                "warning": AMBER_SOFT}.get(status, NEUTRAL_SOFT)
        self.shape = rounded_rect(canvas, 3, 3, width - 3, CARD_HEIGHT - 3, 17, fill=SURFACE,
                                  outline=border, width=3 if focused else (2 if status != "testing" else 1))
        canvas.create_oval(18, 22, 68, 72, fill=soft, outline="")
        draw_icon(canvas, self.device.get("category", "unknown"), color if status != "testing" else MUTED,
                  43, 47, SURFACE)
        canvas.create_text(82, 27, anchor="w", fill=color if status != "testing" else MUTED,
                           text=CATEGORIES.get(self.device.get("category"), "Outro").upper(), font=fonts["tag"])
        canvas.create_text(82, 50, anchor="w", width=width - 100, fill=INK, font=fonts["card"],
                           text=self.device.get("name") or "Equipamento sem nome")
        weight = (self.result or {}).get("weight") or self.device.get("weight")
        footer = port_text(self.device) + (f"  ·  {weight}" if weight else "")
        canvas.create_text(20, 101, anchor="w", width=width - 130, fill=MUTED, font=fonts["small"],
                           text=footer)
        canvas.create_text(width - 20, 101, anchor="e", fill=color, font=fonts["tag_big"], text=label)

    def pulse(self, on: bool) -> None:
        if self.shape is None or not self.active or self.app.focus_get() is self.canvas:
            return
        self.canvas.itemconfigure(self.shape, outline=GREEN_GLOW if on else GREEN, width=3 if on else 2)


class DetailWindow(tk.Toplevel):
    """Two-column technical details of one peripheral, refreshed after each test."""

    def __init__(self, app: "HipautoDesktop", device_id: str):
        super().__init__(app)
        self.app, self.device_id = app, device_id
        self.title("Detalhes do periférico")
        self.geometry("680x600")
        self.minsize(560, 460)
        self.configure(bg=BG)
        self.transient(app)
        fonts = app.fonts
        head = tk.Frame(self, bg=HEADER, padx=22, pady=16)
        head.pack(fill="x")
        self.kind = tk.Label(head, bg=HEADER, fg=GREEN_GLOW, font=fonts["tag"])
        self.kind.pack(anchor="w")
        self.name = tk.Label(head, bg=HEADER, fg="white", font=fonts["heading"], anchor="w",
                             justify="left", wraplength=620)
        self.name.pack(anchor="w", fill="x")
        actions = tk.Frame(self, bg=BG, padx=18)
        actions.pack(side="bottom", fill="x", pady=(0, 16))
        ttk.Button(actions, text="Fechar", style="Secondary.TButton", command=self.destroy).pack(side="right")
        self.test_button = ttk.Button(actions, text="Testar comunicação", style="Primary.TButton",
                                      command=lambda: app.test_one(device_id))
        self.test_button.pack(side="right", padx=8)
        holder = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=LINE)
        holder.pack(fill="both", expand=True, padx=18, pady=18)
        self.body = ScrollFrame(holder, bg=SURFACE)
        self.body.pack(fill="both", expand=True, padx=2, pady=2)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()
        self.after_idle(self._grab)

    def _grab(self, attempts: int = 40) -> None:
        """Make the window modal once it is mapped, without blocking the event loop."""
        try:
            if not self.winfo_exists():
                return
            if not self.winfo_viewable():
                if attempts:
                    self.after(50, self._grab, attempts - 1)
                return
            self.grab_set()
            self.test_button.focus_set()
        except tk.TclError:
            pass  # janela fechada antes de aparecer

    def refresh(self) -> None:
        device = self.app.device_by_id(self.device_id)
        if device is None:
            self.destroy()
            return
        result = self.app.results.get(self.device_id)
        self.kind.configure(text=CATEGORIES.get(device.get("category"), "Periférico").upper())
        self.name.configure(text=device.get("name") or "Equipamento")
        self.test_button.state(["disabled" if self.app.busy else "!disabled"])
        inner = self.body.inner
        for child in inner.winfo_children():
            child.destroy()
        fonts = self.app.fonts
        for row, (label, value) in enumerate(detail_rows(device, result)):
            bg = STRIPE if row % 2 == 0 else SURFACE
            tk.Label(inner, text=label, bg=bg, fg=MUTED, font=fonts["label"], anchor="nw", padx=12,
                     pady=8).grid(row=row, column=0, sticky="nsew")
            tk.Label(inner, text=value, bg=bg, fg=INK, font=fonts["body"], anchor="w", justify="left",
                     wraplength=410, padx=12, pady=8).grid(row=row, column=1, sticky="nsew")
        inner.grid_columnconfigure(0, weight=1, minsize=150)
        inner.grid_columnconfigure(1, weight=3)


class HipautoDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HIPAUTO · Diagnóstico do PDV")
        self.geometry("1180x780")
        self.minsize(900, 620)
        self.configure(bg=BG)
        self.devices: list[dict[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.environment: dict[str, Any] = {}
        self.notices: list[dict[str, str]] = []
        self.cards: dict[str, DeviceCard] = {}
        self.details: DetailWindow | None = None
        self.busy = False
        self._columns = 0
        self._pulse_on = False
        self._alive = True
        self._loaded = False
        self._events: "queue.Queue[tuple[Callable[..., None], tuple]]" = queue.Queue()
        self.status_var = tk.StringVar(value="Preparando diagnóstico local…")
        self.summary_var = tk.StringVar(value="Nenhum periférico carregado")
        self.notice_var = tk.StringVar()
        family = pick_font(self)
        self.fonts = {"brand": (family, 20, "bold"), "title": (family, 19, "bold"),
                      "heading": (family, 16, "bold"), "section": (family, 12, "bold"),
                      "card": (family, 11, "bold"), "body": (family, 10), "label": (family, 10, "bold"),
                      "small": (family, 9), "tag": (family, 8, "bold"), "tag_big": (family, 9, "bold")}
        self._style(family)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F5>", lambda _e: self.refresh_devices())
        self.bind("<Control-t>", lambda _e: self.test_all())
        self.after(60, self._drain_events)
        self.after(150, self.refresh_devices)
        self.after(700, self._pulse)

    # ------------------------------------------------------------------ layout
    def _style(self, family: str) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Primary.TButton", background=BRAND, foreground="white", font=(family, 10, "bold"),
                        padding=(16, 10), borderwidth=0)
        style.map("Primary.TButton", background=[("disabled", "#9aadb5"), ("active", "#066b76")],
                  foreground=[("disabled", "#eef3f5")])
        style.configure("Secondary.TButton", font=(family, 10), padding=(14, 10))
        style.configure("Treeview", rowheight=36, font=(family, 10), background=SURFACE,
                        fieldbackground=SURFACE, borderwidth=0)
        style.configure("Treeview.Heading", font=(family, 10, "bold"), padding=9, background="#e7eef3",
                        foreground=INK)
        style.map("Treeview", background=[("selected", "#d9eef0")], foreground=[("selected", INK)])

    def _build(self) -> None:
        fonts = self.fonts
        header = tk.Frame(self, bg=HEADER, padx=26, pady=17)
        header.pack(fill="x")
        tk.Label(header, text="H", bg="#20b7aa", fg="white", font=fonts["brand"], width=3).pack(
            side="left", padx=(0, 14))
        heading = tk.Frame(header, bg=HEADER)
        heading.pack(side="left")
        tk.Label(heading, text="Diagnóstico do PDV", bg=HEADER, fg="white", font=fonts["title"]).pack(anchor="w")
        tk.Label(heading, text="Periféricos conectados a este computador", bg=HEADER, fg="#b9ceda",
                 font=fonts["small"]).pack(anchor="w")
        tk.Label(header, text="●  OPERAÇÃO LOCAL", bg=HEADER, fg=GREEN_GLOW, font=fonts["tag_big"]).pack(side="right")

        footer = tk.Frame(self, bg=BG, padx=26, pady=12)
        footer.pack(side="bottom", fill="x")
        self.version_label = tk.Label(footer, text=f"v{__version__}", bg="#dfe7ec", fg="#41515c",
                                      font=fonts["tag"], padx=6, pady=3)
        self.version_label.pack(side="left")
        tk.Label(footer, text="Clique em um card para ver os detalhes · F5 atualiza · Ctrl+T testa todos",
                 bg=BG, fg=MUTED, font=fonts["small"]).pack(side="left", padx=10)

        toolbar = tk.Frame(self, bg=BG, padx=26)
        toolbar.pack(fill="x", pady=(15, 10))
        title = tk.Frame(toolbar, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Periféricos", bg=BG, fg=INK, font=fonts["heading"]).pack(anchor="w")
        tk.Label(title, textvariable=self.status_var, bg=BG, fg=MUTED, font=fonts["small"]).pack(anchor="w")
        self.test_all_button = ttk.Button(toolbar, text="Testar todos", style="Primary.TButton",
                                          command=self.test_all)
        self.test_all_button.pack(side="right")
        self.refresh_button = ttk.Button(toolbar, text="Atualizar", style="Secondary.TButton",
                                         command=self.refresh_devices)
        self.refresh_button.pack(side="right", padx=(0, 9))

        self.notice_bar = tk.Frame(self, bg=AMBER_SOFT, padx=16, pady=9, highlightthickness=1,
                                   highlightbackground="#f1d19b")
        self.notice_label = tk.Label(self.notice_bar, textvariable=self.notice_var, bg=AMBER_SOFT, fg="#6b4300",
                                     font=fonts["small"], justify="left", anchor="w")
        self.notice_label.pack(fill="x")
        self.notice_bar.bind("<Configure>", lambda e: self.notice_label.configure(wraplength=max(200, e.width - 40)))

        self.card_scroll = ScrollFrame(self, bg=BG, fixed_height=True, padx=21)
        self.card_scroll.pack(fill="x")
        self.card_area = self.card_scroll.inner
        self.card_scroll.canvas.bind("<Configure>", self._layout_cards, add="+")
        self.empty_label = tk.Label(self.card_area, bg=BG, fg=MUTED, font=fonts["body"],
                                    text="Procurando periféricos…", pady=30)

        section = tk.Frame(self, bg=BG, padx=26)
        section.pack(fill="both", expand=True, pady=(14, 0))
        bar = tk.Frame(section, bg=SURFACE, padx=18, pady=11, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x")
        tk.Label(bar, text="Resumo dos testes", bg=SURFACE, fg=INK, font=fonts["section"]).pack(side="left")
        tk.Label(bar, textvariable=self.summary_var, bg=SURFACE, fg=MUTED, font=fonts["small"]).pack(side="right")
        table = tk.Frame(section, bg=SURFACE, highlightthickness=1, highlightbackground=LINE)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("device", "port", "test"), show="headings", selectmode="browse")
        for key, label, width in (("device", "Periférico", 340), ("port", "Porta", 220), ("test", "Resultado", 460)):
            self.tree.heading(key, text=label, anchor="w")
            self.tree.column(key, width=width, minwidth=120, stretch=True, anchor="w")
        self.tree.tag_configure("ok", foreground="#087b56")
        self.tree.tag_configure("detected", foreground=INK)
        self.tree.tag_configure("warning", foreground=AMBER)
        self.tree.tag_configure("error", foreground=RED)
        self.tree.tag_configure("testing", foreground=BRAND)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for sequence in ("<Double-1>", "<Return>"):
            self.tree.bind(sequence, lambda _e: self._open_selected())

    # --------------------------------------------------------------- threading
    def _post(self, callback: Callable[..., None], *args: Any) -> None:
        """Called from worker threads; the callback runs later on the Tk thread."""
        self._events.put((callback, args))

    def _drain_events(self) -> None:
        if not self._alive:
            return
        while True:
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        self.after(60, self._drain_events)

    def _set_busy(self, value: bool) -> None:
        self.busy = value
        for button in (self.refresh_button, self.test_all_button):
            button.state(["disabled" if value else "!disabled"])
        if self.details is not None and self.details.winfo_exists():
            self.details.test_button.state(["disabled" if value else "!disabled"])

    def run_job(self, message: str, task: Callable[[], Any], done: Callable[[Any, Exception | None], None]) -> bool:
        if self.busy:
            self.bell()
            return False
        self._set_busy(True)
        self.status_var.set(message)

        def worker() -> None:
            try:
                value, error = task(), None
            except Exception as exc:
                value, error = None, exc
            self._post(self._finish_job, done, value, error)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _finish_job(self, done: Callable[[Any, Exception | None], None], value: Any, error: Exception | None) -> None:
        self._set_busy(False)
        done(value, error)

    def close(self) -> None:
        self._alive = False
        try:
            for pending in self.tk.splitlist(self.tk.call("after", "info")):
                self.tk.call("after", "cancel", pending)  # o destroy libera os comandos Tcl
        except tk.TclError:
            pass
        self.destroy()

    # ----------------------------------------------------------------- actions
    def device_by_id(self, device_id: str) -> dict[str, Any] | None:
        return next((device for device in self.devices if device["id"] == device_id), None)

    def refresh_devices(self) -> None:
        def task() -> tuple[list[dict[str, Any]], dict[str, Any]]:
            devices = discovery.discover()
            return devices, environment.snapshot()

        def done(value: Any, error: Exception | None) -> None:
            if error:
                self.status_var.set("Não foi possível atualizar a lista")
                messagebox.showerror("Falha no diagnóstico", str(error), parent=self)
                return
            self.devices, self.environment = value
            self._loaded = True
            known = {device["id"] for device in self.devices}
            self.results = {key: item for key, item in self.results.items() if key in known}
            self.notices = [item for item in environment.recommendations(self.devices, self.environment)
                            if item["severity"] in {"warning", "error"}]
            self._refresh_view()
            self.status_var.set(time.strftime("Atualizado às %H:%M:%S"))
            if self.details is not None and self.details.winfo_exists():
                self.details.refresh()

        self.run_job("Procurando periféricos conectados…", task, done)

    def _test(self, devices: list[dict[str, Any]], message: str) -> None:
        targets = list(devices)

        def task() -> dict[str, int]:
            counts = {"ok": 0, "warning": 0, "error": 0}
            for index, device in enumerate(targets, 1):
                outcome = checks.test_device(device)
                counts[outcome.get("status") if outcome.get("status") in counts else "warning"] += 1
                self._post(self._apply_result, device["id"], outcome, index, len(targets))
            return counts

        def done(counts: Any, error: Exception | None) -> None:
            if error:
                messagebox.showerror("Falha nos testes", str(error), parent=self)
                return
            parts = [f"{counts['ok']} OK"]
            if counts["warning"]:
                parts.append(f"{counts['warning']} com atenção")
            if counts["error"]:
                parts.append(f"{counts['error']} com falha")
            self.status_var.set(f"Testes concluídos às {time.strftime('%H:%M:%S')}: {', '.join(parts)}")

        if self.run_job(message, task, done):
            for device in targets:
                self.results[device["id"]] = {"status": "testing", "detail": "Teste em andamento"}
            self._refresh_view()

    def test_all(self) -> None:
        if not self.devices:
            messagebox.showinfo("Nenhum equipamento", "Nenhum periférico foi encontrado.", parent=self)
            return
        self._test(self.devices, "Testando todos os periféricos…")

    def test_one(self, device_id: str) -> None:
        device = self.device_by_id(device_id)
        if device is not None:
            self._test([device], f"Testando {device.get('name') or 'equipamento'}…")

    def _apply_result(self, device_id: str, outcome: dict[str, Any], index: int, total: int) -> None:
        if self.device_by_id(device_id) is None:
            return
        self.results[device_id] = outcome
        if total > 1 and index < total:
            self.status_var.set(f"Testando {index + 1} de {total}…")
        self._refresh_view()
        if self.details is not None and self.details.winfo_exists() and self.details.device_id == device_id:
            self.details.refresh()

    def _open_selected(self) -> None:
        selected = self.tree.selection()
        if selected:
            self.open_details(selected[0])

    def open_details(self, device_id: str) -> None:
        if self.device_by_id(device_id) is None:
            return
        if self.details is not None and self.details.winfo_exists():
            self.details.destroy()
        self.details = DetailWindow(self, device_id)

    # ------------------------------------------------------------------- views
    def _refresh_view(self) -> None:
        self._render_cards()
        self._render_table()
        self._render_notices()

    def _render_notices(self) -> None:
        if self.notices:
            self.notice_var.set("\n".join(f"⚠  {item['text']}" for item in self.notices))
            if not self.notice_bar.winfo_ismapped():
                self.notice_bar.pack(fill="x", padx=26, pady=(0, 10), before=self.card_scroll)
        else:
            self.notice_bar.pack_forget()

    def _render_cards(self) -> None:
        ids = {device["id"] for device in self.devices}
        for device_id in [key for key in self.cards if key not in ids]:
            self.cards.pop(device_id).canvas.destroy()
        for device in self.devices:
            card = self.cards.get(device["id"])
            if card is None:
                card = self.cards[device["id"]] = DeviceCard(self, self.card_area, device)
            card.update(device, self.results.get(device["id"]))
        self._columns = 0
        self._layout_cards()

    def _layout_cards(self, _event: tk.Event | None = None) -> None:
        width = self.card_scroll.canvas.winfo_width()
        columns = max(1, min(4, (width if width > 1 else 1100) // CARD_MIN_WIDTH))
        if columns == self._columns and _event is not None:
            return
        self._columns = columns
        for column in range(4):
            self.card_area.grid_columnconfigure(column, weight=1 if column < columns else 0,
                                                uniform="cards" if column < columns else "")
        if not self.devices:
            self.empty_label.configure(text="Nenhum periférico encontrado. Confira cabos e energia e "
                                            "clique em Atualizar." if self._loaded
                                       else "Procurando periféricos…")
            self.empty_label.grid(row=0, column=0, columnspan=columns, sticky="ew")
        else:
            self.empty_label.grid_forget()
        for index, device in enumerate(self.devices):
            self.cards[device["id"]].canvas.grid(row=index // columns, column=index % columns,
                                                 sticky="nsew", padx=5, pady=5)
        rows = max(1, min(VISIBLE_CARD_ROWS, -(-len(self.devices) // columns)))
        self.card_scroll.canvas.configure(height=rows * (CARD_HEIGHT + 10) + 2)
        self.card_scroll.after_idle(self.card_scroll._sync)

    def _render_table(self) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for device in self.devices:
            result = self.results.get(device["id"])
            status = current_status(device, result)
            detail = (result or {}).get("detail") or device.get("detail") or "Aguardando teste"
            weight = (result or {}).get("weight")
            if weight:
                detail = f"{detail} · {weight}"
            self.tree.insert("", "end", iid=device["id"], tags=(status,), values=(
                device.get("name") or CATEGORIES.get(device.get("category"), "Outro"),
                port_text(device), f"{status_label(status)} · {detail}"))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        tested = [r for key, r in self.results.items() if r.get("status") not in (None, "testing")]
        failed = sum(r.get("status") == "error" for r in tested)
        active = sum(current_status(d, self.results.get(d["id"])) in ACTIVE for d in self.devices)
        summary = f"{len(self.devices)} periférico(s) · {active} ativo(s)"
        if tested:
            summary += f" · {len(tested)} testado(s)"
        if failed:
            summary += f" · {failed} com falha"
        self.summary_var.set(summary)

    def _pulse(self) -> None:
        if not self._alive:
            return
        self._pulse_on = not self._pulse_on
        for card in self.cards.values():
            card.pulse(self._pulse_on)
        self.after(700, self._pulse)

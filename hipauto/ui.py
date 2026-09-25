"""Interface desktop (Tk) do HIPAUTO.

Camadas visuais: hero com wallpaper técnico, indicadores que também filtram, cards
animados por periférico, resumo tabular, notificações e janela de detalhes em seções.
Toda a lógica pesada roda em threads; a interface só é tocada na thread do Tk.
"""

from __future__ import annotations

import math
import queue
from functools import lru_cache
import socket
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import __version__, checks, discovery, environment
from .icons import (connection_kind, draw_connection, draw_glyph, draw_icon, draw_wallpaper, mix,
                    rounded_rect)

# ------------------------------------------------------------------ tokens visuais
BG = "#eef2f6"
SURFACE = "#ffffff"
STRIPE = "#f6f9fb"
LINE = "#dbe3ea"
SHADOW = "#d3dde6"
INK = "#0f2233"
MUTED = "#5f7482"
HEADER = "#0b2536"
HEADER_END = "#0f3b50"
BRAND = "#0a8f98"
BRAND_DARK = "#07717a"
BRAND_SOFT = "#e0f4f5"
ACCENT = "#22c3b1"
GREEN = "#149e6e"
GREEN_GLOW = "#5fe0b1"
GREEN_SOFT = "#def7ec"
RED = "#d64550"
RED_SOFT = "#fdeced"
AMBER = "#b86e00"
AMBER_SOFT = "#fff4e0"
NEUTRAL_SOFT = "#edf2f5"

CATEGORIES = {"pinpad": "Pinpad", "scanner": "Leitor de código", "scale": "Balança",
              "printer": "Impressora", "keyboard": "Teclado", "biometric": "Biometria",
              "touchscreen": "Tela touch", "monitor": "Monitor", "sat": "SAT / MF-e",
              "cash_drawer": "Gaveta", "customer_display": "Display de cliente",
              "card_reader": "Leitor de cartão", "unknown": "Outro"}
STATUS = {"detected": ("Conectado", GREEN, GREEN_SOFT, "●"), "ok": ("OK", GREEN, GREEN_SOFT, "✓"),
          "warning": ("Atenção", AMBER, AMBER_SOFT, "▲"), "error": ("Falha", RED, RED_SOFT, "✕"),
          "testing": ("Testando", BRAND, BRAND_SOFT, "◌")}
ACTIVE = {"ok", "detected"}
FILTERS = (("all", "Periféricos", "grid", BRAND), ("active", "Ativos", "check", GREEN),
           ("warning", "Atenção", "warning", AMBER), ("error", "Falhas", "close", RED))
CARD_HEIGHT = 140
CARD_MIN_WIDTH = 262
VISIBLE_CARD_ROWS = 2
FRAME_MS = 70


def pick_font(root: tk.Misc) -> str:
    families = set(tkfont.families(root))
    return next((name for name in ("Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans", "Segoe UI")
                 if name in families), "TkDefaultFont")


def current_status(device: dict[str, Any], result: dict[str, Any] | None) -> str:
    return (result or {}).get("status") or device.get("status") or "detected"


def status_label(status: str) -> str:
    return STATUS.get(status, (str(status).title(),))[0]


def status_style(status: str) -> tuple[str, str, str, str]:
    return STATUS.get(status, (status_label(status), MUTED, NEUTRAL_SOFT, "•"))


def port_text(device: dict[str, Any]) -> str:
    path = str(device.get("path") or "")
    if not device.get("port") and path.startswith("/sys/bus/usb/devices/"):
        return f"Porta USB {path.rsplit('/', 1)[-1]}"
    return (device.get("port") or device.get("port_name") or device.get("queue")
            or device.get("path") or "Sem porta")


def matches_filter(status: str, name: str) -> bool:
    return name == "all" or (name == "active" and status in ACTIVE) or status == name


def subtitle(device: dict[str, Any]) -> str:
    name = str(device.get("name", "")).lower()
    parts = [str(p) for p in (device.get("manufacturer"), device.get("model")) if p and str(p).lower() not in name]
    if device.get("adapter"):
        parts.append(f"via {device['adapter']}")
    if device.get("resolution"):
        parts.append(device["resolution"])
    return " · ".join(parts) or device.get("connection") or ""


def detail_sections(device: dict[str, Any], result: dict[str, Any] | None) -> list[tuple[str, list[tuple[str, str]]]]:
    """Sections of label/value pairs for the details window; empty values are omitted."""
    merged = dict(device)
    merged.update(result or {})
    hom = merged.get("homologation") or {}
    conf = merged.get("confidence") or {}
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
    sections = [
        ("Identificação", [
            ("Tipo", CATEGORIES.get(merged.get("category"), "Outro")),
            ("Equipamento", merged.get("name")),
            ("Fabricante", merged.get("manufacturer")),
            ("Modelo", merged.get("model")),
            ("Número de série", merged.get("serial_number")),
            ("Firmware", merged.get("firmware")),
            ("Homologação", homologation),
        ]),
        ("Conexão", [
            ("Conexão", merged.get("connection")),
            ("Porta", port_text(device)),
            ("Porta recomendada", merged.get("recommended_port")
             if merged.get("recommended_port") != device.get("port") else None),
            ("Adaptador", merged.get("adapter")),
            ("Configuração serial", serial_config),
            ("Fila CUPS", merged.get("queue")),
            ("Resolução", merged.get("resolution")),
            ("Tamanho", f"{merged['diagonal']} polegadas" if merged.get("diagonal") else None),
        ]),
        ("Resultado do teste", [
            ("Estado", status_label(current_status(device, result))),
            ("Resultado", merged.get("detail")),
            ("Peso", merged.get("weight")),
            ("Protocolo", merged.get("scale_protocol") or merged.get("printer_protocol")),
            ("Resposta (hex)", merged.get("hex")),
            ("Testado às", merged.get("tested_at")),
        ]),
        ("Rastreabilidade técnica", [
            ("Driver", merged.get("driver")),
            ("VID / PID", " / ".join(filter(None, [merged.get("vendor_id"), merged.get("product_id")]))),
            ("Linguagem", merged.get("commands")),
            ("Confiança", " · ".join(filter(None, [conf.get("label"), conf.get("reason")]))
             if isinstance(conf, dict) else conf),
            ("Evidências", "\n".join(merged.get("evidence") or [])),
        ]),
    ]
    cleaned = []
    for title, rows in sections:
        rows = [(label, str(value)) for label, value in rows if value not in (None, "", [])]
        if rows:
            cleaned.append((title, rows))
    return cleaned


def detail_rows(device: dict[str, Any], result: dict[str, Any] | None) -> list[tuple[str, str]]:
    return [row for _title, rows in detail_sections(device, result) for row in rows]


# ------------------------------------------------------------------ componentes
class FlatButton(tk.Canvas):
    """Rounded button with icon, hover/press/focus states and a ttk-like state API."""

    VARIANTS = {"primary": (BRAND, BRAND_DARK, "#ffffff", ""),
                "secondary": (SURFACE, "#f1f5f8", INK, LINE),
                "ghost": (BG, "#e3eaf0", INK, "")}

    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None], icon: str | None = None,
                 variant: str = "secondary", font: tuple = ("TkDefaultFont", 10, "bold"), bg: str = BG):
        self.text, self.command, self.icon, self.variant, self.font = text, command, icon, variant, font
        self.text_width = tkfont.Font(font=font).measure(text)
        self.w, self.h = self.text_width + (58 if icon else 36), 42
        super().__init__(master, width=self.w, height=self.h, bg=bg, highlightthickness=0, cursor="hand2",
                         takefocus=1)
        self._disabled = self._hover = self._pressed = False
        for sequence, handler in (("<Enter>", lambda _e: self._set(hover=True)),
                                  ("<Leave>", lambda _e: self._set(hover=False, pressed=False)),
                                  ("<ButtonPress-1>", lambda _e: self._set(pressed=True)),
                                  ("<ButtonRelease-1>", self._release),
                                  ("<Return>", lambda _e: self.invoke()), ("<space>", lambda _e: self.invoke()),
                                  ("<FocusIn>", lambda _e: self.draw()), ("<FocusOut>", lambda _e: self.draw())):
            self.bind(sequence, handler)
        self.draw()

    def _set(self, **flags: bool) -> None:
        for key, value in flags.items():
            setattr(self, f"_{key}", value)
        self.draw()

    def _release(self, event: tk.Event) -> None:
        inside = 0 <= event.x <= self.w and 0 <= event.y <= self.h
        self._set(pressed=False)
        if inside:
            self.invoke()

    def invoke(self) -> None:
        if not self._disabled:
            self.command()

    def state(self, flags: list[str]) -> None:
        for flag in flags:
            if flag in {"disabled", "!disabled"}:
                self._disabled = flag == "disabled"
        self.configure(cursor="arrow" if self._disabled else "hand2")
        self.draw()

    def instate(self, flags: list[str]) -> bool:
        return all((flag == "disabled") == self._disabled for flag in flags if flag in {"disabled", "!disabled"})

    def draw(self) -> None:
        self.delete("all")
        base, hover, fg, border = self.VARIANTS[self.variant]
        fill = hover if (self._hover or self._pressed) and not self._disabled else base
        if self._disabled:
            primary = self.variant == "primary"
            fill, fg = ("#a9bcc4", "#eef3f5") if primary else ("#f3f6f8", "#9aabb6")
        offset = 1 if self._pressed else 0
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        if focused:
            rounded_rect(self, 1, 1, self.w - 1, self.h - 1, 12, fill="", outline=ACCENT, width=2)
        rounded_rect(self, 3, 3 + offset, self.w - 3, self.h - 3 + offset, 10, fill=fill,
                     outline=border or fill, width=1)
        x = self.w / 2
        if self.icon:
            start = (self.w - self.text_width - 22) / 2
            draw_glyph(self, self.icon, fg, start + 7, self.h / 2 + offset, 0.9)
            x = start + 22 + self.text_width / 2
        self.create_text(x, self.h / 2 + offset, text=self.text, fill=fg, font=self.font)


class ProgressLine(tk.Canvas):
    """3px progress indicator: determinate (fraction) or indeterminate (sliding)."""

    def __init__(self, master: tk.Misc):
        super().__init__(master, height=3, bg=BG, highlightthickness=0)
        self.fraction: float | None = None
        self.active = False

    def start(self, fraction: float | None = None) -> None:
        self.active, self.fraction = True, fraction

    def stop(self) -> None:
        self.active = False
        self.delete("all")

    def tick(self, phase: float) -> None:
        if not self.active:
            return
        self.delete("all")
        width = max(self.winfo_width(), 1)
        self.create_rectangle(0, 0, width, 3, fill=LINE, outline="")
        if self.fraction is None:
            head = (phase * 0.9 % 1.4 - 0.2) * width
            self.create_rectangle(max(0, head), 0, min(width, head + width * 0.22), 3, fill=BRAND, outline="")
        else:
            self.create_rectangle(0, 0, width * max(0.02, self.fraction), 3, fill=BRAND, outline="")


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
        if not self.winfo_exists():
            return
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
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            if active:
                self.canvas.bind_all(sequence, self._on_wheel)
            else:
                self.canvas.unbind_all(sequence)

    def _on_wheel(self, event: tk.Event) -> None:
        if not self.scrollbar.winfo_ismapped():
            return
        step = -1 if getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(step, "units")


class KpiTile(tk.Canvas):
    """Indicator tile that doubles as a status filter."""

    def __init__(self, app: "HipautoDesktop", master: tk.Misc, key: str, label: str, glyph: str, color: str):
        super().__init__(master, height=76, bg=BG, highlightthickness=0, cursor="hand2", takefocus=1)
        self.app, self.key, self.label, self.glyph, self.color = app, key, label, glyph, color
        self.value, self.selected, self.hover = 0, key == "all", False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            self.bind(sequence, lambda _e: app.set_filter(key))

    def _hover(self, value: bool) -> None:
        self.hover = value
        self.draw()

    def update_tile(self, value: int, selected: bool) -> None:
        self.value, self.selected = value, selected
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 160)
        fonts = self.app.fonts
        border = self.color if self.selected else (mix(LINE, self.color, .35) if self.hover else LINE)
        fill = mix(SURFACE, self.color, .06) if self.selected else SURFACE
        rounded_rect(self, 2, 2, width - 2, 74, 14, fill=fill, outline=border, width=2 if self.selected else 1)
        self.create_oval(18, 18, 58, 58, fill=mix(SURFACE, self.color, .14), outline="")
        draw_glyph(self, self.glyph, self.color, 38, 38, 1.1)
        self.create_text(74, 30, anchor="w", text=str(self.value), fill=INK, font=fonts["kpi"])
        self.create_text(74, 54, anchor="w", text=self.label.upper(), fill=MUTED, font=fonts["tag"])
        if self.selected and self.key != "all":
            self.create_text(width - 16, 20, anchor="e", text="FILTRO ATIVO", fill=self.color, font=fonts["tag"])


class DeviceCard:
    """One animated, clickable and keyboard-focusable peripheral card."""

    def __init__(self, app: "HipautoDesktop", parent: tk.Misc, device: dict[str, Any]):
        self.app, self.device, self.result = app, device, None
        self.shape: int | None = None
        self.spinner: int | None = None
        self.hover = False
        self.canvas = tk.Canvas(parent, height=CARD_HEIGHT, bg=BG, highlightthickness=0, cursor="hand2",
                                takefocus=1)
        self.canvas.bind("<Configure>", lambda _e: self.draw())
        for sequence in ("<Button-1>", "<Return>", "<KP_Enter>", "<space>"):
            self.canvas.bind(sequence, lambda _e: self.app.open_details(self.device["id"]))
        for sequence, value in (("<Enter>", True), ("<Leave>", False)):
            self.canvas.bind(sequence, lambda _e, v=value: self._hover(v))
        self.canvas.bind("<FocusIn>", lambda _e: self.draw())
        self.canvas.bind("<FocusOut>", lambda _e: self.draw())

    @property
    def status(self) -> str:
        return current_status(self.device, self.result)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE

    def _hover(self, value: bool) -> None:
        self.hover = value
        self.draw()

    def _focused(self) -> bool:
        try:
            return self.app.focus_get() is self.canvas
        except (KeyError, tk.TclError):
            return False

    def update(self, device: dict[str, Any], result: dict[str, Any] | None) -> None:
        self.device, self.result = device, result
        self.draw()

    def draw(self) -> None:
        canvas, fonts = self.canvas, self.app.fonts
        canvas.delete("all")
        width = max(canvas.winfo_width(), CARD_MIN_WIDTH) if canvas.winfo_width() > 1 else CARD_MIN_WIDTH
        status = self.status
        label, color, soft, symbol = status_style(status)
        focused = self._focused()
        lift = 2 if self.hover or focused else 0
        if lift:
            rounded_rect(canvas, 6, 8, width - 2, CARD_HEIGHT - 1, 17, fill=SHADOW, outline="")
        border = ACCENT if focused else (LINE if status == "testing" else color)
        self.shape = rounded_rect(canvas, 3, 5 - lift, width - 5, CARD_HEIGHT - 5 - lift, 16, fill=SURFACE,
                                  outline=border, width=2 if status != "testing" or focused else 1)
        top = 2 - lift
        icon_color = MUTED if status == "testing" else color
        canvas.create_oval(18, 20 + top, 64, 66 + top, fill=soft, outline="")
        draw_icon(canvas, self.device.get("category", "unknown"), icon_color, 41, 43 + top, SURFACE)
        self.spinner = None
        if status == "testing":
            self.spinner = canvas.create_arc(14, 16 + top, 68, 70 + top, start=0, extent=80, style="arc",
                                             outline=BRAND, width=3)
        pill_text = f"{symbol} {label}"
        pill_width = self.app.measure("tag_big", pill_text) + 20
        rounded_rect(canvas, width - 18 - pill_width, 16 + top, width - 18, 38 + top, 11, fill=soft, outline="")
        canvas.create_text(width - 18 - pill_width / 2, 27 + top, text=pill_text, fill=color, font=fonts["tag_big"])
        canvas.create_text(78, 27 + top, anchor="w", fill=icon_color, font=fonts["tag"], width=width - 110 - pill_width,
                           text=CATEGORIES.get(self.device.get("category"), "Outro").upper())
        canvas.create_text(78, 54 + top, anchor="w", width=width - 100, fill=INK, font=fonts["card"],
                           text=self.device.get("name") or "Equipamento sem nome")
        sub = subtitle(self.device)
        if sub:
            canvas.create_text(78, 80 + top, anchor="w", width=width - 100, fill=MUTED, font=fonts["small"],
                               text=sub)
        canvas.create_line(18, 96 + top, width - 22, 96 + top, fill=LINE)
        draw_connection(canvas, connection_kind(self.device.get("connection")), MUTED, 28, 116 + top)
        weight = (self.result or {}).get("weight") or self.device.get("weight")
        canvas.create_text(42, 116 + top, anchor="w", width=width - 150, fill=MUTED, font=fonts["small"],
                           text=port_text(self.device))
        if weight:
            chip = f"⚖ {weight}"
            chip_width = self.app.measure("tag_big", chip) + 18
            rounded_rect(canvas, width - 22 - chip_width, 105 + top, width - 22, 127 + top, 10, fill=BRAND_SOFT,
                         outline="")
            canvas.create_text(width - 22 - chip_width / 2, 116 + top, text=chip, fill=BRAND_DARK,
                               font=fonts["tag_big"])
        elif self.hover or focused:
            canvas.create_text(width - 22, 116 + top, anchor="e", text="Detalhes  ›", fill=BRAND,
                               font=fonts["tag_big"])

    def animate(self, phase: float) -> None:
        if self.spinner is not None:
            self.canvas.itemconfigure(self.spinner, start=(-phase * 240) % 360)
        elif self.shape is not None and self.active and not self.hover and not self._focused():
            wave = (math.sin(phase * 2.2) + 1) / 2
            self.canvas.itemconfigure(self.shape, outline=mix(GREEN, GREEN_GLOW, wave), width=2 + wave)


class Toast:
    """Transient notification sliding in at the bottom-right corner."""

    def __init__(self, app: "HipautoDesktop", text: str, kind: str = "ok"):
        _label, color, soft, _symbol = status_style(kind)
        self.app = app
        self.frame = tk.Frame(app, bg=SURFACE, highlightthickness=1, highlightbackground=mix(LINE, color, .4))
        tk.Frame(self.frame, bg=color, width=4).pack(side="left", fill="y")
        icon = tk.Canvas(self.frame, width=34, height=34, bg=SURFACE, highlightthickness=0)
        icon.pack(side="left", padx=(10, 0), pady=10)
        icon.create_oval(3, 3, 31, 31, fill=soft, outline="")
        draw_glyph(icon, {"ok": "check", "warning": "warning", "error": "close"}.get(kind, "pulse"), color, 17, 17, .9)
        self.label = tk.Label(self.frame, text=text, bg=SURFACE, fg=INK, font=app.fonts["body"], justify="left",
                              wraplength=320)
        self.label.pack(side="left", padx=(10, 16), pady=10)
        self.offset = 40
        self._slide()
        app.after(4200, self.close)

    def _slide(self) -> None:
        if not self.frame.winfo_exists():
            return
        self.frame.place(relx=1, rely=1, anchor="se", x=-24, y=-58 + self.offset)
        if self.offset > 0:
            self.offset = max(0, self.offset - 8)
            self.app.after(16, self._slide)

    def close(self) -> None:
        if self.frame.winfo_exists():
            self.frame.destroy()


class DetailWindow(tk.Toplevel):
    """Sectioned technical details of one peripheral, refreshed after each test."""

    def __init__(self, app: "HipautoDesktop", device_id: str):
        super().__init__(app)
        self.app, self.device_id = app, device_id
        self.title("Detalhes do periférico")
        self.geometry("720x680")
        self.minsize(600, 520)
        self.configure(bg=BG)
        self.transient(app)
        self.hero = tk.Canvas(self, height=118, bg=HEADER, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", lambda _e: self._draw_hero())
        actions = tk.Frame(self, bg=BG, padx=18)
        actions.pack(side="bottom", fill="x", pady=(0, 16))
        FlatButton(actions, "Fechar", self.destroy, "close", "ghost", app.fonts["button"]).pack(side="right")
        self.test_button = FlatButton(actions, "Testar comunicação", lambda: app.test_one(device_id), "play",
                                      "primary", app.fonts["button"])
        self.test_button.pack(side="right", padx=8)
        FlatButton(actions, "Copiar dados", self.copy, "copy", "secondary", app.fonts["button"]).pack(side="left")
        holder = tk.Frame(self, bg=SURFACE, highlightthickness=1, highlightbackground=LINE)
        holder.pack(fill="both", expand=True, padx=18, pady=16)
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

    def _draw_hero(self) -> None:
        device = self.app.device_by_id(self.device_id)
        if device is None:
            return
        canvas, fonts = self.hero, self.app.fonts
        width = max(canvas.winfo_width(), 600)
        canvas.delete("all")
        draw_wallpaper(canvas, width, 118, HEADER, HEADER_END, "#153a4d", "#1d5266", ACCENT, seed=3)
        status = current_status(device, self.app.results.get(self.device_id))
        label, color, soft, symbol = status_style(status)
        canvas.create_oval(24, 26, 90, 92, fill=mix(HEADER, "#ffffff", .1), outline=mix(HEADER, ACCENT, .5))
        draw_icon(canvas, device.get("category", "unknown"), "#e8fbf7", 57, 59, HEADER)
        canvas.create_text(108, 34, anchor="w", text=CATEGORIES.get(device.get("category"), "Periférico").upper(),
                           fill=GREEN_GLOW, font=fonts["tag"])
        canvas.create_text(108, 60, anchor="w", width=width - 260, text=device.get("name") or "Equipamento",
                           fill="#ffffff", font=fonts["heading"])
        canvas.create_text(108, 88, anchor="w", width=width - 260, text=subtitle(device), fill="#b9ceda",
                           font=fonts["small"])
        pill = f"{symbol} {label}"
        pill_width = self.app.measure("tag_big", pill) + 24
        rounded_rect(canvas, width - 24 - pill_width, 22, width - 24, 48, 13, fill=soft, outline="")
        canvas.create_text(width - 24 - pill_width / 2, 35, text=pill, fill=color, font=fonts["tag_big"])

    def refresh(self) -> None:
        device = self.app.device_by_id(self.device_id)
        if device is None:
            self.destroy()
            return
        result = self.app.results.get(self.device_id)
        self._draw_hero()
        self.test_button.state(["disabled" if self.app.busy else "!disabled"])
        inner = self.body.inner
        for child in inner.winfo_children():
            child.destroy()
        fonts = self.app.fonts
        row = 0
        for title, rows in detail_sections(device, result):
            tk.Label(inner, text=title.upper(), bg=SURFACE, fg=BRAND, font=fonts["tag"], anchor="w",
                     padx=12, pady=8).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8 if row else 0, 0))
            row += 1
            for index, (label, value) in enumerate(rows):
                bg = STRIPE if index % 2 == 0 else SURFACE
                tk.Label(inner, text=label, bg=bg, fg=MUTED, font=fonts["label"], anchor="nw", padx=12,
                         pady=7).grid(row=row, column=0, sticky="nsew")
                tk.Label(inner, text=value, bg=bg, fg=INK, font=fonts["body"], anchor="w", justify="left",
                         wraplength=440, padx=12, pady=7).grid(row=row, column=1, sticky="nsew")
                row += 1
        inner.grid_columnconfigure(0, weight=1, minsize=160)
        inner.grid_columnconfigure(1, weight=3)

    def copy(self) -> None:
        device = self.app.device_by_id(self.device_id)
        if device is None:
            return
        lines = [f"HIPAUTO · {device.get('name')}"]
        for title, rows in detail_sections(device, self.app.results.get(self.device_id)):
            lines.append(f"\n[{title}]")
            lines.extend(f"{label}: {value}" for label, value in rows)
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.app.toast("Dados do periférico copiados para a área de transferência.", "ok")


# ------------------------------------------------------------------ janela principal
class HipautoDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HIPAUTO · Diagnóstico do PDV")
        self.geometry("1240x840")
        self.minsize(960, 680)
        self.configure(bg=BG)
        self.devices: list[dict[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.environment: dict[str, Any] = {}
        self.notices: list[dict[str, str]] = []
        self.cards: dict[str, DeviceCard] = {}
        self.tiles: dict[str, KpiTile] = {}
        self.details: DetailWindow | None = None
        self.filter = "all"
        self.busy = False
        self._columns = 0
        self._phase = 0.0
        self._alive = True
        self._loaded = False
        self._events: "queue.Queue[tuple[Callable[..., None], tuple]]" = queue.Queue()
        self.status_var = tk.StringVar(value="Preparando diagnóstico local…")
        self.summary_var = tk.StringVar(value="Nenhum periférico carregado")
        self.notice_var = tk.StringVar()
        family = pick_font(self)
        self.fonts = {"brand": (family, 22, "bold"), "title": (family, 21, "bold"), "kpi": (family, 20, "bold"),
                      "heading": (family, 16, "bold"), "section": (family, 12, "bold"),
                      "card": (family, 11, "bold"), "body": (family, 10), "label": (family, 10, "bold"),
                      "button": (family, 10, "bold"), "small": (family, 9), "tag": (family, 8, "bold"),
                      "tag_big": (family, 9, "bold")}
        self.measure = lru_cache(maxsize=1024)(
            lambda key, text: tkfont.Font(root=self, font=self.fonts[key]).measure(text))
        self._style(family)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<F5>", lambda _e: self.refresh_devices())
        self.bind("<Control-t>", lambda _e: self.test_all())
        self.bind("<Escape>", lambda _e: self.set_filter("all") if self.filter != "all" else None)
        self.after(60, self._drain_events)
        self.after(150, self.refresh_devices)
        self.after(FRAME_MS, self._animate)

    # ------------------------------------------------------------------ layout
    def _style(self, family: str) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=36, font=(family, 10), background=SURFACE, fieldbackground=SURFACE,
                        borderwidth=0, foreground=INK)
        style.configure("Treeview.Heading", font=(family, 9, "bold"), padding=(10, 9), background="#e9f0f4",
                        foreground=MUTED, relief="flat", borderwidth=0)
        style.map("Treeview.Heading", background=[("active", "#dfe8ee")])
        style.map("Treeview", background=[("selected", "#d4eef0")], foreground=[("selected", INK)])
        style.configure("Vertical.TScrollbar", background="#dfe7ec", troughcolor=BG, borderwidth=0,
                        arrowsize=12, gripcount=0)

    def _build(self) -> None:
        fonts = self.fonts
        self.host = socket.gethostname()
        self.hero = tk.Canvas(self, height=128, bg=HEADER, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", lambda _e: self._draw_hero())

        footer = tk.Frame(self, bg=BG, padx=26, pady=12)
        footer.pack(side="bottom", fill="x")
        self.version_label = tk.Label(footer, text=f"v{__version__}", bg="#dfe7ec", fg="#41515c",
                                      font=fonts["tag"], padx=6, pady=3)
        self.version_label.pack(side="left")
        hint = tk.Frame(footer, bg=BG)
        hint.pack(side="left", padx=12)
        for key, text in (("F5", "atualiza"), ("Ctrl+T", "testa todos"), ("Enter", "abre detalhes"),
                          ("Esc", "limpa filtro")):
            tk.Label(hint, text=key, bg=SURFACE, fg=INK, font=fonts["tag"], padx=5, pady=1, relief="solid",
                     borderwidth=1).pack(side="left", padx=(0, 4))
            tk.Label(hint, text=text, bg=BG, fg=MUTED, font=fonts["small"]).pack(side="left", padx=(0, 12))

        kpis = tk.Frame(self, bg=BG, padx=21)
        kpis.pack(fill="x", pady=(16, 0))
        for column, (key, label, glyph, color) in enumerate(FILTERS):
            tile = self.tiles[key] = KpiTile(self, kpis, key, label, glyph, color)
            tile.grid(row=0, column=column, sticky="ew", padx=5)
            kpis.grid_columnconfigure(column, weight=1, uniform="kpi")

        toolbar = tk.Frame(self, bg=BG, padx=26)
        toolbar.pack(fill="x", pady=(16, 8))
        title = tk.Frame(toolbar, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Periféricos", bg=BG, fg=INK, font=fonts["heading"]).pack(anchor="w")
        tk.Label(title, textvariable=self.status_var, bg=BG, fg=MUTED, font=fonts["small"]).pack(anchor="w")
        self.test_all_button = FlatButton(toolbar, "Testar todos", self.test_all, "play", "primary", fonts["button"])
        self.test_all_button.pack(side="right")
        self.refresh_button = FlatButton(toolbar, "Atualizar", self.refresh_devices, "refresh", "secondary",
                                         fonts["button"])
        self.refresh_button.pack(side="right", padx=(0, 8))
        self.progress = ProgressLine(self)
        self.progress.pack(fill="x", padx=26, pady=(0, 10))

        self.notice_bar = tk.Frame(self, bg=AMBER_SOFT, padx=12, pady=8, highlightthickness=1,
                                   highlightbackground="#f1d19b")
        notice_icon = tk.Canvas(self.notice_bar, width=22, height=22, bg=AMBER_SOFT, highlightthickness=0)
        notice_icon.pack(side="left", anchor="n", padx=(0, 8))
        draw_glyph(notice_icon, "warning", AMBER, 11, 12, .9)
        self.notice_label = tk.Label(self.notice_bar, textvariable=self.notice_var, bg=AMBER_SOFT, fg="#6b4300",
                                     font=fonts["small"], justify="left", anchor="w")
        self.notice_label.pack(side="left", fill="x", expand=True)
        self.notice_bar.bind("<Configure>", lambda e: self.notice_label.configure(wraplength=max(200, e.width - 60)))

        self.card_scroll = ScrollFrame(self, bg=BG, fixed_height=True, padx=21)
        self.card_scroll.pack(fill="x")
        self.card_area = self.card_scroll.inner
        self.card_scroll.canvas.bind("<Configure>", self._layout_cards, add="+")
        self.empty_state = tk.Frame(self.card_area, bg=BG)
        self.empty_art = tk.Canvas(self.empty_state, width=80, height=70, bg=BG, highlightthickness=0)
        self.empty_art.pack(pady=(18, 4))
        draw_glyph(self.empty_art, "plug", "#9fb2bf", 40, 36, 1.6)
        self.empty_label = tk.Label(self.empty_state, bg=BG, fg=MUTED, font=fonts["body"],
                                    text="Procurando periféricos…")
        self.empty_label.pack(pady=(0, 18))

        section = tk.Frame(self, bg=BG, padx=26)
        section.pack(fill="both", expand=True, pady=(12, 0))
        bar = tk.Frame(section, bg=SURFACE, padx=18, pady=11, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x")
        pulse = tk.Canvas(bar, width=22, height=20, bg=SURFACE, highlightthickness=0)
        pulse.pack(side="left", padx=(0, 6))
        draw_glyph(pulse, "pulse", BRAND, 11, 10, .9)
        tk.Label(bar, text="Resumo dos testes", bg=SURFACE, fg=INK, font=fonts["section"]).pack(side="left")
        tk.Label(bar, textvariable=self.summary_var, bg=SURFACE, fg=MUTED, font=fonts["small"]).pack(side="right")
        table = tk.Frame(section, bg=SURFACE, highlightthickness=1, highlightbackground=LINE)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("device", "port", "test"), show="headings", selectmode="browse")
        for key, label, width in (("device", "PERIFÉRICO", 340), ("port", "PORTA", 220), ("test", "RESULTADO", 480)):
            self.tree.heading(key, text=label, anchor="w")
            self.tree.column(key, width=width, minwidth=120, stretch=True, anchor="w")
        for status, (_label, color, _soft, _symbol) in STATUS.items():
            self.tree.tag_configure(status, foreground=INK if status == "detected" else color)
        self.tree.tag_configure("stripe", background=STRIPE)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for sequence in ("<Double-1>", "<Return>"):
            self.tree.bind(sequence, lambda _e: self._open_selected())

    def _draw_hero(self) -> None:
        canvas, fonts = self.hero, self.fonts
        width = max(canvas.winfo_width(), 900)
        canvas.delete("all")
        draw_wallpaper(canvas, width, 128, HEADER, HEADER_END, "#12384b", "#1b4f63", ACCENT)
        rounded_rect(canvas, 28, 36, 84, 92, 16, fill=ACCENT, outline="")
        canvas.create_text(56, 64, text="H", fill="#ffffff", font=fonts["brand"])
        canvas.create_text(104, 52, anchor="w", text="Diagnóstico do PDV", fill="#ffffff", font=fonts["title"])
        canvas.create_text(104, 82, anchor="w", text="Identificação e teste dos periféricos deste computador",
                           fill="#b9ceda", font=fonts["small"])
        x = width - 28
        for text, glyph, color in (("OPERAÇÃO LOCAL", None, GREEN_GLOW), (self.host, "host", "#d7e6ee")):
            label = canvas.create_text(x - 16, 63, anchor="e", text=text, fill=color, font=fonts["tag_big"])
            left = canvas.bbox(label)[0] - 30
            chip = rounded_rect(canvas, left, 48, x, 78, 15, fill=mix(HEADER, "#ffffff", .08),
                                outline=mix(HEADER, "#ffffff", .18))
            canvas.tag_lower(chip, label)
            if glyph:
                draw_glyph(canvas, glyph, color, left + 17, 63, .9)
            else:
                canvas.create_oval(left + 12, 59, left + 20, 67, fill=color, outline="")
            x = left - 10

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
        if value:
            self.progress.start()
        else:
            self.progress.stop()

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

    def toast(self, text: str, kind: str = "ok") -> None:
        for child in self.place_slaves():
            child.destroy()
        Toast(self, text, kind)

    # ----------------------------------------------------------------- actions
    def device_by_id(self, device_id: str) -> dict[str, Any] | None:
        return next((device for device in self.devices if device["id"] == device_id), None)

    def visible_devices(self) -> list[dict[str, Any]]:
        return [d for d in self.devices if matches_filter(current_status(d, self.results.get(d["id"])), self.filter)]

    def set_filter(self, name: str) -> None:
        self.filter = "all" if name == self.filter else name
        self._refresh_view()

    def refresh_devices(self) -> None:
        started = time.monotonic()

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
            elapsed = time.monotonic() - started
            self.status_var.set(time.strftime("Atualizado às %H:%M:%S") + f" · varredura em {elapsed:.1f} s")
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
            summary = ", ".join(parts)
            self.status_var.set(f"Testes concluídos às {time.strftime('%H:%M:%S')}: {summary}")
            kind = "error" if counts["error"] else ("warning" if counts["warning"] else "ok")
            self.toast(f"Testes concluídos: {summary}.", kind)

        if self.run_job(message, task, done):
            self.progress.start(0.0)
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
        self.progress.fraction = index / total
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
        self._render_tiles()
        self._render_cards()
        self._render_table()
        self._render_notices()

    def _render_tiles(self) -> None:
        statuses = [current_status(d, self.results.get(d["id"])) for d in self.devices]
        for key, tile in self.tiles.items():
            tile.update_tile(sum(matches_filter(status, key) for status in statuses), key == self.filter)

    def _render_notices(self) -> None:
        if self.notices:
            self.notice_var.set("\n".join(item["text"] for item in self.notices))
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
        columns = max(1, min(4, (width if width > 1 else 1180) // CARD_MIN_WIDTH))
        if columns == self._columns and _event is not None:
            return
        self._columns = columns
        for column in range(4):
            self.card_area.grid_columnconfigure(column, weight=1 if column < columns else 0,
                                                uniform="cards" if column < columns else "")
        visible = self.visible_devices()
        for card in self.cards.values():
            card.canvas.grid_forget()
        if not visible:
            if not self._loaded:
                text = "Procurando periféricos…"
            elif self.devices:
                text = "Nenhum periférico neste filtro. Clique no indicador de novo ou pressione Esc."
            else:
                text = "Nenhum periférico encontrado. Confira cabos e energia e clique em Atualizar."
            self.empty_label.configure(text=text)
            self.empty_state.grid(row=0, column=0, columnspan=columns, sticky="ew")
        else:
            self.empty_state.grid_forget()
        for index, device in enumerate(visible):
            self.cards[device["id"]].canvas.grid(row=index // columns, column=index % columns,
                                                 sticky="nsew", padx=5, pady=5)
        rows = max(1, min(VISIBLE_CARD_ROWS, -(-len(visible) // columns))) if visible else 1
        self.card_scroll.canvas.configure(height=rows * (CARD_HEIGHT + 10) + 2 if visible else 150)
        self.card_scroll.after_idle(self.card_scroll._sync)

    def _render_table(self) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for row, device in enumerate(self.visible_devices()):
            result = self.results.get(device["id"])
            status = current_status(device, result)
            label, _color, _soft, symbol = status_style(status)
            detail = (result or {}).get("detail") or device.get("detail") or "Aguardando teste"
            weight = (result or {}).get("weight")
            if weight:
                detail = f"{detail} · {weight}"
            tags = (status, "stripe") if row % 2 else (status,)
            self.tree.insert("", "end", iid=device["id"], tags=tags, values=(
                device.get("name") or CATEGORIES.get(device.get("category"), "Outro"),
                port_text(device), f"{symbol}  {label} · {detail}"))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        tested = [r for r in self.results.values() if r.get("status") not in (None, "testing")]
        failed = sum(r.get("status") == "error" for r in tested)
        active = sum(current_status(d, self.results.get(d["id"])) in ACTIVE for d in self.devices)
        summary = f"{len(self.devices)} periférico(s) · {active} ativo(s)"
        if tested:
            summary += f" · {len(tested)} testado(s)"
        if failed:
            summary += f" · {failed} com falha"
        if self.filter != "all":
            summary += f" · filtro: {dict((k, l) for k, l, _g, _c in FILTERS)[self.filter]}"
        self.summary_var.set(summary)

    def _animate(self) -> None:
        if not self._alive:
            return
        self._phase += FRAME_MS / 1000
        for card in self.cards.values():
            card.animate(self._phase)
        self.progress.tick(self._phase)
        self.after(FRAME_MS, self._animate)

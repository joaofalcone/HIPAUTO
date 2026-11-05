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
MUTED = "#526775"
HEADER = "#0b2536"
HEADER_END = "#0f3b50"
BRAND = "#087c84"
BRAND_DARK = "#066a72"
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
# Cores de texto (contraste mínimo 4,5:1 sobre o fundo suave do próprio estado);
# as cores vivas acima ficam para bordas, ícones e indicadores gráficos.
GREEN_TEXT = "#0b7650"
RED_TEXT = "#b42f3a"
AMBER_TEXT = "#935600"
BRAND_TEXT = "#066a72"
STATUS_TEXT = {"detected": GREEN_TEXT, "ok": GREEN_TEXT, "warning": AMBER_TEXT, "error": RED_TEXT,
               "testing": BRAND_TEXT}

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
FILTER_HINTS = {"all": "Mostrar todos os periféricos", "active": "Mostrar só os conectados e OK",
                "warning": "Mostrar só os que pedem atenção", "error": "Mostrar só as falhas"}
CARD_HEIGHT = 140
CARD_MIN_WIDTH = 262
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


def status_text(status: str) -> str:
    return STATUS_TEXT.get(status, MUTED)


def fit_text(measure: Callable[[str], int], text: str, width: float, lines: int = 1) -> str:
    """Wrap text into at most `lines` lines of `width` pixels, ending with "…" if cut."""
    words, result, current = str(text or "").split(), [], ""
    while words:
        candidate = f"{current} {words[0]}".strip()
        if measure(candidate) <= width:
            current, words = candidate, words[1:]
            continue
        if not current:  # uma palavra sozinha maior que a linha
            current, words = words[0], words[1:]
        result.append(current)
        current = ""
        if len(result) == lines:
            break
    if current:
        result.append(current)
    cut = bool(words) or len(result) > lines
    result = result[:lines]
    if result and (cut or measure(result[-1]) > width):
        last = result[-1]
        while last and measure(last + "…") > width:
            last = last[:-1]
        result[-1] = last.rstrip() + "…"
    return "\n".join(result)


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


class Tooltip:
    """Small delayed hint window; one shared instance per application."""

    def __init__(self, app: "HipautoDesktop"):
        self.app, self.window, self.job = app, None, None

    def schedule(self, widget: tk.Misc, text_source: Callable[[], str], delay: int = 650) -> None:
        self.cancel()
        self.job = self.app.after(delay, lambda: self.show(widget, text_source()))

    def show(self, widget: tk.Misc, text: str) -> None:
        self.job = None
        if not text or not widget.winfo_exists() or not widget.winfo_viewable():
            return
        self.hide()
        window = self.window = tk.Toplevel(self.app)
        window.wm_overrideredirect(True)
        window.configure(bg=LINE)
        tk.Label(window, text=text, bg=INK, fg="#ffffff", font=self.app.fonts["small"], justify="left",
                 wraplength=360, padx=10, pady=6).pack(padx=1, pady=1)
        x = widget.winfo_pointerx() + 14
        y = widget.winfo_pointery() + 18
        window.wm_geometry(f"+{x}+{y}")

    def cancel(self) -> None:
        if self.job is not None:
            self.app.after_cancel(self.job)
            self.job = None
        self.hide()

    def hide(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()
        self.window = None


def attach_tooltip(app: "HipautoDesktop", widget: tk.Misc, text_source: Callable[[], str]) -> None:
    widget.bind("<Enter>", lambda _e: app.tooltip.schedule(widget, text_source), add="+")
    for sequence in ("<Leave>", "<ButtonPress>", "<KeyPress>"):
        widget.bind(sequence, lambda _e: app.tooltip.cancel(), add="+")


class SegmentedControl(tk.Canvas):
    """Two or more mutually exclusive options drawn as one rounded control."""

    def __init__(self, app: "HipautoDesktop", master: tk.Misc, options: list[tuple[str, str, str]],
                 command: Callable[[str], None]):
        self.app, self.options, self.command = app, options, command
        self.value = options[0][0]
        self.widths = [app.measure("button", label) + 46 for _key, label, _glyph in options]
        super().__init__(master, width=sum(self.widths) + 8, height=42, bg=BG, highlightthickness=0,
                         cursor="hand2", takefocus=1)
        self.hover: str | None = None
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Left>", lambda _e: self._step(-1))
        self.bind("<Right>", lambda _e: self._step(1))
        self.bind("<FocusIn>", lambda _e: self.draw())
        self.bind("<FocusOut>", lambda _e: self.draw())
        self.draw()

    def _key_at(self, x: float) -> str | None:
        left = 4
        for (key, _label, _glyph), width in zip(self.options, self.widths):
            if left <= x <= left + width:
                return key
            left += width
        return None

    def _set_hover(self, key: str | None) -> None:
        if key != self.hover:
            self.hover = key
            self.draw()

    def _motion(self, event: tk.Event) -> None:
        self._set_hover(self._key_at(event.x))

    def _click(self, event: tk.Event) -> None:
        key = self._key_at(event.x)
        if key:
            self.select(key)

    def _step(self, delta: int) -> None:
        keys = [key for key, _label, _glyph in self.options]
        self.select(keys[(keys.index(self.value) + delta) % len(keys)])

    def select(self, key: str) -> None:
        if key != self.value:
            self.value = key
            self.draw()
            self.command(key)

    def draw(self) -> None:
        self.delete("all")
        fonts = self.app.fonts
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        total = sum(self.widths) + 8
        rounded_rect(self, 1, 1, total - 1, 41, 12, fill="", outline=ACCENT if focused else BG, width=2)
        rounded_rect(self, 3, 3, total - 3, 39, 10, fill="#e3eaf0", outline="")
        left = 4
        for (key, label, glyph), width in zip(self.options, self.widths):
            selected = key == self.value
            if selected:
                rounded_rect(self, left + 1, 6, left + width - 1, 36, 8, fill=SURFACE, outline=LINE)
            color = INK if selected else (BRAND_TEXT if key == self.hover else MUTED)
            draw_glyph(self, glyph, color, left + 20, 21, .8)
            self.create_text(left + 34, 21, anchor="w", text=label, fill=color, font=fonts["button"])
            left += width


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
        self.compact = False
        self.value, self.selected, self.hover = 0, key == "all", False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            self.bind(sequence, lambda _e: app.set_filter(key))
        self.bind("<FocusIn>", lambda _e: self.draw())
        self.bind("<FocusOut>", lambda _e: self.draw())
        attach_tooltip(app, self, lambda: FILTER_HINTS[key] + (" (ativo; clique de novo para limpar)"
                                                               if self.selected and key != "all" else ""))

    def _hover(self, value: bool) -> None:
        self.hover = value
        self.draw()

    def update_tile(self, value: int, selected: bool) -> None:
        self.value, self.selected = value, selected
        self.draw()

    def set_compact(self, compact: bool) -> None:
        if compact != self.compact:
            self.compact = compact
            self.configure(height=56 if compact else 76)
            self.draw()

    def draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 160)
        fonts = self.app.fonts
        border = self.color if self.selected else (mix(LINE, self.color, .35) if self.hover else LINE)
        fill = mix(SURFACE, self.color, .06) if self.selected else SURFACE
        height = 56 if self.compact else 76
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        if focused:
            rounded_rect(self, 0, 0, width, height, 16, fill="", outline=ACCENT, width=2)
        rounded_rect(self, 2, 2, width - 2, height - 2, 14, fill=fill, outline=border, width=2 if self.selected else 1)
        middle, radius = height / 2, (14 if self.compact else 20)
        self.create_oval(18, middle - radius, 18 + 2 * radius, middle + radius, fill=mix(SURFACE, self.color, .14),
                         outline="")
        draw_glyph(self, self.glyph, self.color, 18 + radius, middle, .9 if self.compact else 1.1)
        text_x = 30 + 2 * radius
        if self.compact:
            value = self.create_text(text_x, middle, anchor="w", text=str(self.value), fill=INK,
                                     font=fonts["heading"])
            self.create_text(self.bbox(value)[2] + 10, middle + 1, anchor="w", text=self.label.upper(),
                             fill=MUTED, font=fonts["tag"])
        else:
            self.create_text(text_x, 30, anchor="w", text=str(self.value), fill=INK, font=fonts["kpi"])
            self.create_text(text_x, 54, anchor="w", text=self.label.upper(), fill=MUTED, font=fonts["tag"])
        if self.selected and self.key != "all":
            text_color = {GREEN: GREEN_TEXT, AMBER: AMBER_TEXT, RED: RED_TEXT}.get(self.color, BRAND_TEXT)
            self.create_text(width - 16, 16 if self.compact else 20, anchor="e", text="FILTRO ATIVO", fill=text_color,
                             font=fonts["tag"])


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
        for sequence, delta in (("<Left>", (0, -1)), ("<Right>", (0, 1)), ("<Up>", (-1, 0)), ("<Down>", (1, 0))):
            self.canvas.bind(sequence, lambda _e, d=delta: self.app.move_card_focus(self.device["id"], *d))
        attach_tooltip(app, self.canvas, self.hint)

    def hint(self) -> str:
        result = self.result or {}
        lines = [self.device.get("name") or "Equipamento", port_text(self.device)]
        detail = result.get("detail") or self.device.get("detail")
        if detail:
            lines.append(f"{status_label(self.status)} · {detail}")
        return "\n".join(lines)

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
        measure = self.app.measure
        text_color = MUTED if status == "testing" else status_text(status)
        pill_text = f"{symbol} {label}"
        pill_width = measure("tag_big", pill_text) + 20
        rounded_rect(canvas, width - 18 - pill_width, 16 + top, width - 18, 38 + top, 11, fill=soft, outline="")
        canvas.create_text(width - 18 - pill_width / 2, 27 + top, text=pill_text, fill=status_text(status),
                           font=fonts["tag_big"])
        category = CATEGORIES.get(self.device.get("category"), "Outro").upper()
        canvas.create_text(78, 27 + top, anchor="w", fill=text_color, font=fonts["tag"],
                           text=fit_text(lambda t: measure("tag", t), category, width - 110 - pill_width))
        name = fit_text(lambda t: measure("card", t), self.device.get("name") or "Equipamento sem nome",
                        width - 100, lines=2)
        canvas.create_text(78, 54 + top, anchor="w", fill=INK, font=fonts["card"], text=name)
        sub = subtitle(self.device)
        if sub:
            canvas.create_text(78, 80 + top, anchor="w", fill=MUTED, font=fonts["small"],
                               text=fit_text(lambda t: measure("small", t), sub, width - 100))
        canvas.create_line(18, 96 + top, width - 22, 96 + top, fill=LINE)
        draw_connection(canvas, connection_kind(self.device.get("connection")), MUTED, 28, 116 + top)
        weight = (self.result or {}).get("weight") or self.device.get("weight")
        canvas.create_text(42, 116 + top, anchor="w", fill=MUTED, font=fonts["small"],
                           text=fit_text(lambda t: measure("small", t), port_text(self.device), width - 160))
        if weight:
            chip = f"⚖ {weight}"
            chip_width = self.app.measure("tag_big", chip) + 18
            rounded_rect(canvas, width - 22 - chip_width, 105 + top, width - 22, 127 + top, 10, fill=BRAND_SOFT,
                         outline="")
            canvas.create_text(width - 22 - chip_width / 2, 116 + top, text=chip, fill=BRAND_DARK,
                               font=fonts["tag_big"])
        elif self.hover or focused:
            canvas.create_text(width - 22, 116 + top, anchor="e", text="Detalhes  ›", fill=BRAND_TEXT,
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
        for widget in (self.frame, icon, self.label):
            widget.bind("<Button-1>", lambda _e: self.close())
            widget.configure(cursor="hand2")
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
        width = min(720, app.winfo_width() - 40) if app.winfo_width() > 700 else 720
        height = min(680, max(520, app.winfo_height() - 60))
        x = app.winfo_rootx() + max(0, (app.winfo_width() - width) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(560, 460)
        self.wrap = 440
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
        self.body.canvas.bind("<Configure>", self._rewrap, add="+")
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

    def _rewrap(self, event: tk.Event) -> None:
        wrap = max(220, event.width - 210)
        if abs(wrap - self.wrap) < 8:
            return
        self.wrap = wrap
        for child in self.body.inner.grid_slaves(column=1):
            child.configure(wraplength=wrap)

    def _draw_hero(self) -> None:
        device = self.app.device_by_id(self.device_id)
        if device is None:
            return
        canvas, fonts = self.hero, self.app.fonts
        width = max(canvas.winfo_width(), 400)
        canvas.delete("all")
        draw_wallpaper(canvas, width, 118, HEADER, HEADER_END, "#153a4d", "#1d5266", ACCENT, seed=3)
        status = current_status(device, self.app.results.get(self.device_id))
        label, color, soft, symbol = status_style(status)
        canvas.create_oval(24, 26, 90, 92, fill=mix(HEADER, "#ffffff", .1), outline=mix(HEADER, ACCENT, .5))
        draw_icon(canvas, device.get("category", "unknown"), "#e8fbf7", 57, 59, HEADER)
        canvas.create_text(108, 34, anchor="w", text=CATEGORIES.get(device.get("category"), "Periférico").upper(),
                           fill=GREEN_GLOW, font=fonts["tag"])
        measure = self.app.measure
        canvas.create_text(108, 60, anchor="w", fill="#ffffff", font=fonts["heading"],
                           text=fit_text(lambda t: measure("heading", t), device.get("name") or "Equipamento",
                                         width - 270))
        canvas.create_text(108, 88, anchor="w", fill="#b9ceda", font=fonts["small"],
                           text=fit_text(lambda t: measure("small", t), subtitle(device), width - 270))
        pill = f"{symbol} {label}"
        pill_width = self.app.measure("tag_big", pill) + 24
        rounded_rect(canvas, width - 24 - pill_width, 22, width - 24, 48, 13, fill=soft, outline="")
        canvas.create_text(width - 24 - pill_width / 2, 35, text=pill, fill=status_text(status), font=fonts["tag_big"])

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
            tk.Label(inner, text=title.upper(), bg=SURFACE, fg=BRAND_TEXT, font=fonts["tag"], anchor="w",
                     padx=12, pady=8).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8 if row else 0, 0))
            row += 1
            for index, (label, value) in enumerate(rows):
                bg = STRIPE if index % 2 == 0 else SURFACE
                tk.Label(inner, text=label, bg=bg, fg=MUTED, font=fonts["label"], anchor="nw", padx=12,
                         pady=7).grid(row=row, column=0, sticky="nsew")
                tk.Label(inner, text=value, bg=bg, fg=INK, font=fonts["body"], anchor="w", justify="left",
                         wraplength=self.wrap, padx=12, pady=7).grid(row=row, column=1, sticky="nsew")
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
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = min(1240, screen_w - 40), min(840, screen_h - 80)
        self.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 3)}")
        self.minsize(min(900, width), min(600, height))
        if screen_w <= 1366 and screen_h <= 768:
            try:
                self.attributes("-zoomed", True)  # telas típicas de PDV: aproveita a tela toda
            except tk.TclError:
                pass
        self.configure(bg=BG)
        self.devices: list[dict[str, Any]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.environment: dict[str, Any] = {}
        self.notices: list[dict[str, str]] = []
        self.cards: dict[str, DeviceCard] = {}
        self.tiles: dict[str, KpiTile] = {}
        self.details: DetailWindow | None = None
        self.filter = "all"
        self.view = "cards"
        self.compact = False
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
        self.tooltip = Tooltip(self)
        self._style(family)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Configure>", self._on_resize, add="+")
        self.bind("<F5>", lambda _e: self.refresh_devices())
        self.bind("<Control-t>", lambda _e: self.test_all())
        self.bind("<Escape>", lambda _e: self.set_filter("all") if self.filter != "all" else None)
        self.bind("<Control-Key-1>", lambda _e: self.view_switch.select("cards"))
        self.bind("<Control-Key-2>", lambda _e: self.view_switch.select("list"))
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
        style.configure("Treeview", rowheight=38, bordercolor=LINE, lightcolor=SURFACE, darkcolor=SURFACE)
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # sem moldura de foco preta
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
        hint = self.footer_hint = tk.Frame(footer, bg=BG)
        hint.pack(side="left", padx=12)
        for key, text in (("F5", "atualiza"), ("Ctrl+T", "testa todos"), ("Ctrl+1/2", "cards ou lista"),
                          ("Setas", "navegam"), ("Esc", "limpa filtro")):
            tk.Label(hint, text=key, bg=SURFACE, fg=INK, font=fonts["tag"], padx=5, pady=1, relief="solid",
                     borderwidth=1).pack(side="left", padx=(0, 4))
            tk.Label(hint, text=text, bg=BG, fg=MUTED, font=fonts["small"]).pack(side="left", padx=(0, 12))

        kpis = self.kpis = tk.Frame(self, bg=BG, padx=21)
        kpis.pack(fill="x", pady=(16, 0))
        for column, (key, label, glyph, color) in enumerate(FILTERS):
            tile = self.tiles[key] = KpiTile(self, kpis, key, label, glyph, color)
            tile.grid(row=0, column=column, sticky="ew", padx=5)
            kpis.grid_columnconfigure(column, weight=1, uniform="kpi")

        toolbar = self.toolbar = tk.Frame(self, bg=BG, padx=26)
        toolbar.pack(fill="x", pady=(16, 8))
        self.test_all_button = FlatButton(toolbar, "Testar todos", self.test_all, "play", "primary", fonts["button"])
        self.test_all_button.pack(side="right")
        self.refresh_button = FlatButton(toolbar, "Atualizar", self.refresh_devices, "refresh", "secondary",
                                         fonts["button"])
        self.refresh_button.pack(side="right", padx=(0, 8))
        self.view_switch = SegmentedControl(self, toolbar, [("cards", "Cards", "grid"), ("list", "Lista", "pulse")],
                                            self.set_view)
        self.view_switch.pack(side="right", padx=(0, 16))
        # Título e status entram por último: em telas estreitas eles cedem espaço aos controles.
        title = tk.Frame(toolbar, bg=BG)
        title.pack(side="left", fill="x", expand=True)
        tk.Label(title, text="Periféricos", bg=BG, fg=INK, font=fonts["heading"], anchor="w").pack(fill="x")
        self.status_label = tk.Label(title, textvariable=self.status_var, bg=BG, fg=MUTED, font=fonts["small"],
                                     anchor="w", justify="left")
        self.status_label.pack(fill="x")
        title.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(120, e.width)))
        attach_tooltip(self, self.refresh_button, lambda: "Procurar periféricos de novo (F5)")
        attach_tooltip(self, self.test_all_button, lambda: "Testar a comunicação de todos (Ctrl+T)")
        attach_tooltip(self, self.view_switch, lambda: "Alternar entre cards e lista (Ctrl+1 / Ctrl+2)")
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

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, pady=(0, 4))
        self.card_scroll = ScrollFrame(self.content, bg=BG, padx=21)
        self.card_scroll.pack(fill="both", expand=True)
        self.card_area = self.card_scroll.inner
        self.card_scroll.canvas.bind("<Configure>", self._layout_cards, add="+")
        self.empty_state = tk.Frame(self.card_area, bg=BG)
        self.empty_art = tk.Canvas(self.empty_state, width=80, height=70, bg=BG, highlightthickness=0)
        self.empty_art.pack(pady=(18, 4))
        draw_glyph(self.empty_art, "plug", "#9fb2bf", 40, 36, 1.6)
        self.empty_label = tk.Label(self.empty_state, bg=BG, fg=MUTED, font=fonts["body"],
                                    text="Procurando periféricos…")
        self.empty_label.pack(pady=(0, 18))

        section = self.list_view = tk.Frame(self.content, bg=BG, padx=26)
        bar = tk.Frame(section, bg=SURFACE, padx=18, pady=11, highlightthickness=1, highlightbackground=LINE)
        bar.pack(fill="x")
        pulse = tk.Canvas(bar, width=22, height=20, bg=SURFACE, highlightthickness=0)
        pulse.pack(side="left", padx=(0, 6))
        draw_glyph(pulse, "pulse", BRAND, 11, 10, .9)
        tk.Label(bar, text="Resumo dos testes", bg=SURFACE, fg=INK, font=fonts["section"]).pack(side="left")
        tk.Label(bar, textvariable=self.summary_var, bg=SURFACE, fg=MUTED, font=fonts["small"]).pack(side="right")
        table = tk.Frame(section, bg=SURFACE, highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("device", "port", "test"), show="headings", selectmode="browse")
        for key, label, width in (("device", "PERIFÉRICO", 340), ("port", "PORTA", 220), ("test", "RESULTADO", 480)):
            self.tree.heading(key, text=label, anchor="w")
            self.tree.column(key, width=width, minwidth=120, stretch=True, anchor="w")
        for status in STATUS:
            self.tree.tag_configure(status, foreground=INK if status == "detected" else status_text(status))
        self.tree.tag_configure("stripe", background=STRIPE)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for sequence in ("<Double-1>", "<Return>"):
            self.tree.bind(sequence, lambda _e: self._open_selected())
        self._tree_widths: tuple[int, ...] = ()
        self.tree.bind("<Configure>", lambda _e: self.after_idle(self._rewrap_table), add="+")
        self.tree.bind("<ButtonRelease-1>", lambda _e: self.after_idle(self._rewrap_table), add="+")

    def _draw_hero(self) -> None:
        canvas, fonts = self.hero, self.fonts
        width, height = max(canvas.winfo_width(), 320), (76 if self.compact else 128)
        middle = height / 2
        canvas.delete("all")
        draw_wallpaper(canvas, width, height, HEADER, HEADER_END, "#12384b", "#1b4f63", ACCENT)
        size = 40 if self.compact else 56
        rounded_rect(canvas, 28, middle - size / 2, 28 + size, middle + size / 2, 12 if self.compact else 16,
                     fill=ACCENT, outline="")
        canvas.create_text(28 + size / 2, middle, text="H", fill="#ffffff",
                           font=fonts["heading"] if self.compact else fonts["brand"])
        title_x = 28 + size + 20
        if self.compact:
            canvas.create_text(title_x, middle, anchor="w", text="Diagnóstico do PDV", fill="#ffffff",
                               font=fonts["heading"])
        else:
            canvas.create_text(title_x, 52, anchor="w", text="Diagnóstico do PDV", fill="#ffffff", font=fonts["title"])
            canvas.create_text(title_x, 82, anchor="w", text="Identificação e teste dos periféricos deste computador",
                               fill="#b9ceda", font=fonts["small"])
        x = width - 28
        chips = [("OPERAÇÃO LOCAL", None, GREEN_GLOW), (self.host, "host", "#d7e6ee")]
        title_end = title_x + self.measure("heading" if self.compact else "title", "Diagnóstico do PDV") + 24
        for text, glyph, color in chips:
            if x - self.measure("tag_big", text) - 46 < title_end:
                break  # sem espaço: o chip some em vez de cobrir o título
            label = canvas.create_text(x - 16, middle - 1, anchor="e", text=text, fill=color, font=fonts["tag_big"])
            left = canvas.bbox(label)[0] - 30
            chip = rounded_rect(canvas, left, middle - 16, x, middle + 14, 15, fill=mix(HEADER, "#ffffff", .08),
                                outline=mix(HEADER, "#ffffff", .18))
            canvas.tag_lower(chip, label)
            if glyph:
                draw_glyph(canvas, glyph, color, left + 17, middle - 1, .9)
            else:
                canvas.create_oval(left + 12, middle - 5, left + 20, middle + 3, fill=color, outline="")
            x = left - 10

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        compact = event.height < 720
        if compact == self.compact:
            return
        self.compact = compact
        self.hero.configure(height=76 if compact else 128)
        for tile in self.tiles.values():
            tile.set_compact(compact)
        self.kpis.pack_configure(pady=(10 if compact else 16, 0))
        self.toolbar.pack_configure(pady=(10 if compact else 16, 6 if compact else 8))
        if compact:
            self.footer_hint.pack_forget()
        else:
            self.footer_hint.pack(side="left", padx=12)
        self._draw_hero()

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

    def set_view(self, view: str) -> None:
        self.view = view
        if view == "list":
            self.card_scroll.pack_forget()
            self.list_view.pack(fill="both", expand=True)
            self.tree.focus_set()
        else:
            self.list_view.pack_forget()
            self.card_scroll.pack(fill="both", expand=True)
        self.view_switch.value = view
        self.view_switch.draw()

    def move_card_focus(self, device_id: str, rows: int, columns: int) -> None:
        ids = [d["id"] for d in self.visible_devices()]
        if device_id not in ids or not self._columns:
            return
        index = ids.index(device_id) + rows * self._columns + columns
        if 0 <= index < len(ids):
            card = self.cards[ids[index]]
            card.canvas.focus_set()
            self._scroll_into_view(card.canvas)

    def _scroll_into_view(self, widget: tk.Misc) -> None:
        canvas = self.card_scroll.canvas
        total = max(1, self.card_area.winfo_height())
        top, bottom = widget.winfo_y(), widget.winfo_y() + widget.winfo_height()
        view_top = canvas.canvasy(0)
        if top < view_top:
            canvas.yview_moveto(top / total)
        elif bottom > view_top + canvas.winfo_height():
            canvas.yview_moveto((bottom - canvas.winfo_height()) / total)

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
                self.notice_bar.pack(fill="x", padx=26, pady=(0, 10), before=self.content)
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
        self.card_scroll.after_idle(self.card_scroll._sync)

    def _rewrap_table(self) -> None:
        """Re-fit cell texts when the columns change width (window resize or drag)."""
        widths = tuple(self.tree.column(key, "width") for key in ("device", "port", "test"))
        if widths != self._tree_widths:
            self._tree_widths = widths
            self._render_table()

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
            values = (device.get("name") or CATEGORIES.get(device.get("category"), "Outro"), port_text(device),
                      f"{symbol}  {label} · {detail}")
            self.tree.insert("", "end", iid=device["id"], tags=tags, values=tuple(
                fit_text(lambda t: self.measure("body", t), value, max(60, self.tree.column(key, "width") - 24))
                for key, value in zip(("device", "port", "test"), values)))
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
        if self.state() != "iconic":  # minimizado: não gasta CPU com animação
            for card in self.cards.values():
                card.animate(self._phase)
            self.progress.tick(self._phase)
        self.after(FRAME_MS, self._animate)

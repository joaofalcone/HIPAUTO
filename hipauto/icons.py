"""Ícones, glifos e padrões vetoriais desenhados no Canvas (nítidos em qualquer escala)."""

from __future__ import annotations

import math
import random
import tkinter as tk


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float = 16,
                 **kwargs) -> int:
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2,
              x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def mix(color_a: str, color_b: str, amount: float) -> str:
    """Linear blend of two #rrggbb colors (0 = a, 1 = b)."""
    amount = max(0.0, min(1.0, amount))
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


# ------------------------------------------------------------------ periféricos
def draw_icon(canvas: tk.Canvas, category: str, color: str, x: float, y: float, fill: str,
              tags: str = "") -> None:
    line = {"fill": color, "width": 2, "capstyle": "round", "tags": tags}
    box = {"fill": "", "outline": color, "width": 2, "tags": tags}
    dot = {"fill": color, "outline": "", "tags": tags}
    if category == "scale":
        canvas.create_line(x - 16, y + 13, x + 16, y + 13, **line)
        canvas.create_rectangle(x - 13, y - 9, x + 13, y + 13, **box)
        canvas.create_arc(x - 8, y - 5, x + 8, y + 11, start=20, extent=140, style="arc", outline=color,
                          width=2, tags=tags)
        canvas.create_line(x, y + 4, x + 4, y - 1, **line)
        canvas.create_line(x - 9, y - 14, x + 9, y - 14, **line)
        canvas.create_line(x, y - 14, x, y - 9, **line)
    elif category == "printer":
        canvas.create_rectangle(x - 11, y - 16, x + 11, y - 6, **box)
        rounded_rect(canvas, x - 17, y - 6, x + 17, y + 10, 4, **box)
        canvas.create_rectangle(x - 10, y + 4, x + 10, y + 17, fill=fill, outline=color, width=2, tags=tags)
        canvas.create_line(x - 6, y + 9, x + 6, y + 9, fill=color, width=1, tags=tags)
        canvas.create_line(x - 6, y + 13, x + 3, y + 13, fill=color, width=1, tags=tags)
        canvas.create_oval(x + 10, y - 2, x + 13, y + 1, **dot)
    elif category == "pinpad":
        rounded_rect(canvas, x - 13, y - 18, x + 13, y + 18, 5, **box)
        canvas.create_rectangle(x - 8, y - 13, x + 8, y - 5, **box)
        for row in range(3):
            for col in range(3):
                cx, cy = x - 7 + col * 7, y + 1 + row * 6
                canvas.create_oval(cx - 1.6, cy - 1.6, cx + 1.6, cy + 1.6, **dot)
    elif category == "keyboard":
        rounded_rect(canvas, x - 19, y - 11, x + 19, y + 11, 4, **box)
        for row in range(2):
            for col in range(6):
                cx, cy = x - 13 + col * 5.2, y - 5 + row * 5.5
                canvas.create_rectangle(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, **dot)
        canvas.create_line(x - 9, y + 6, x + 9, y + 6, **line)
    elif category == "scanner":
        canvas.create_polygon(x - 15, y - 12, x + 7, y - 12, x + 13, y - 4, x - 1, y - 4, x - 5, y + 16,
                              x - 13, y + 16, fill="", outline=color, width=2, joinstyle="round", tags=tags)
        for offset, length in ((-9, 5), (-4, 8), (1, 6), (6, 8), (11, 4)):
            canvas.create_line(x + 15, y + offset, x + 15 + length, y + offset, fill=color, width=1, tags=tags)
    elif category in {"monitor", "touchscreen"}:
        rounded_rect(canvas, x - 18, y - 14, x + 18, y + 9, 3, **box)
        canvas.create_line(x, y + 9, x, y + 15, **line)
        canvas.create_line(x - 9, y + 16, x + 9, y + 16, **line)
        if category == "touchscreen":
            canvas.create_oval(x - 4, y - 7, x + 4, y + 1, outline=color, width=2, tags=tags)
            canvas.create_oval(x - 8, y - 11, x + 8, y + 5, outline=color, width=1, dash=(2, 2), tags=tags)
    elif category == "biometric":
        for inset in (0, 5, 10):
            canvas.create_arc(x - 15 + inset, y - 17 + inset, x + 15 - inset, y + 17 - inset,
                              start=25, extent=285, style="arc", outline=color, width=2, tags=tags)
        canvas.create_line(x, y - 3, x, y + 6, **line)
    elif category == "sat":
        rounded_rect(canvas, x - 16, y - 12, x + 16, y + 12, 4, **box)
        canvas.create_rectangle(x - 10, y - 18, x + 10, y - 12, **box)
        canvas.create_line(x - 9, y - 3, x + 3, y - 3, **line)
        canvas.create_line(x - 9, y + 3, x - 1, y + 3, **line)
        canvas.create_oval(x + 5, y - 1, x + 13, y + 7, outline=color, width=2, tags=tags)
        canvas.create_line(x + 7, y + 3, x + 9, y + 5, x + 12, y + 0, fill=color, width=1.5, tags=tags)
    elif category == "cash_drawer":
        canvas.create_rectangle(x - 18, y - 10, x + 18, y + 14, **box)
        canvas.create_line(x - 18, y - 2, x + 18, y - 2, **line)
        canvas.create_line(x - 6, y + 5, x + 6, y + 5, fill=color, width=3, capstyle="round", tags=tags)
        canvas.create_line(x - 12, y - 10, x - 8, y - 16, x + 8, y - 16, x + 12, y - 10, **line)
    elif category == "customer_display":
        rounded_rect(canvas, x - 18, y - 16, x + 18, y - 2, 3, **box)
        canvas.create_text(x, y - 9, text="R$ 0,00", fill=color, font=("TkFixedFont", 6, "bold"), tags=tags)
        canvas.create_line(x, y - 2, x, y + 14, **line)
        canvas.create_line(x - 10, y + 16, x + 10, y + 16, **line)
    elif category == "card_reader":
        rounded_rect(canvas, x - 18, y - 12, x + 18, y + 12, 4, **box)
        canvas.create_line(x - 18, y - 5, x + 18, y - 5, fill=color, width=4, tags=tags)
        canvas.create_rectangle(x - 12, y + 2, x - 4, y + 8, **box)
    else:
        canvas.create_rectangle(x - 16, y - 10, x + 10, y + 10, **box)
        canvas.create_line(x + 10, y - 5, x + 17, y - 5, x + 17, y + 5, x + 10, y + 5, **line)
        canvas.create_line(x - 11, y - 15, x - 11, y - 10, x + 5, y - 10, x + 5, y - 15, **line)


# ---------------------------------------------------------------- tipos de conexão
def connection_kind(connection: str | None) -> str:
    text = (connection or "").lower()
    for key, kind in (("usb-serial", "serial"), ("usb", "usb"), ("serial", "serial"), ("ps/2", "ps2"),
                      ("rede", "network"), ("bluetooth", "bluetooth"), ("hdmi", "video"),
                      ("displayport", "video"), ("vga", "video"), ("dvi", "video"), ("tela", "video"),
                      ("vídeo", "video"), ("local", "usb")):
        if key in text:
            return kind
    return "generic"


def draw_connection(canvas: tk.Canvas, kind: str, color: str, x: float, y: float) -> None:
    """Tiny 14px connector glyph."""
    line = {"fill": color, "width": 1.5, "capstyle": "round"}
    if kind == "usb":
        canvas.create_line(x, y + 6, x, y - 6, **line)
        canvas.create_polygon(x - 2.5, y - 4, x, y - 7, x + 2.5, y - 4, fill=color, outline=color)
        canvas.create_line(x, y + 2, x - 4, y - 1, x - 4, y - 3, **line)
        canvas.create_line(x, y, x + 4, y - 2, x + 4, y - 4, **line)
        canvas.create_oval(x - 2, y + 5, x + 2, y + 8, fill=color, outline="")
    elif kind == "serial":
        canvas.create_polygon(x - 7, y - 4, x + 7, y - 4, x + 5, y + 4, x - 5, y + 4, fill="", outline=color,
                              width=1.5)
        for px in (-3.5, 0, 3.5):
            canvas.create_oval(x + px - .8, y - 1.5, x + px + .8, y, fill=color, outline="")
        for px in (-1.8, 1.8):
            canvas.create_oval(x + px - .8, y + 1, x + px + .8, y + 2.5, fill=color, outline="")
    elif kind == "ps2":
        canvas.create_oval(x - 6, y - 6, x + 6, y + 6, outline=color, width=1.5)
        for px, py in ((-2.5, -1), (2.5, -1), (-3, 2.5), (3, 2.5)):
            canvas.create_oval(x + px - .8, y + py - .8, x + px + .8, y + py + .8, fill=color, outline="")
    elif kind == "network":
        for px, py in ((0, -5), (-5, 4), (5, 4)):
            canvas.create_oval(x + px - 2, y + py - 2, x + px + 2, y + py + 2, outline=color, width=1.5)
        canvas.create_line(x, y - 3, x - 4, y + 2, **line)
        canvas.create_line(x, y - 3, x + 4, y + 2, **line)
    elif kind == "bluetooth":
        canvas.create_line(x - 4, y - 3, x + 4, y + 3, x, y + 7, x, y - 7, x + 4, y - 3, x - 4, y + 3, **line)
    elif kind == "video":
        canvas.create_polygon(x - 7, y - 3, x + 7, y - 3, x + 7, y + 1, x + 4, y + 4, x - 4, y + 4, x - 7, y + 1,
                              fill="", outline=color, width=1.5)
    else:
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline="")


# ------------------------------------------------------------------ glifos de UI
def draw_glyph(canvas: tk.Canvas, name: str, color: str, x: float, y: float, size: float = 1.0) -> None:
    s = size
    line = {"fill": color, "width": 2, "capstyle": "round", "joinstyle": "round"}
    if name == "refresh":
        canvas.create_arc(x - 6 * s, y - 6 * s, x + 6 * s, y + 6 * s, start=40, extent=280, style="arc",
                          outline=color, width=2)
        canvas.create_polygon(x + 3 * s, y - 8 * s, x + 8 * s, y - 5 * s, x + 3 * s, y - 2 * s, fill=color,
                              outline=color)
    elif name == "play":
        canvas.create_polygon(x - 4 * s, y - 6 * s, x + 6 * s, y, x - 4 * s, y + 6 * s, fill=color, outline=color,
                              joinstyle="round")
    elif name == "copy":
        canvas.create_rectangle(x - 6 * s, y - 3 * s, x + 3 * s, y + 7 * s, outline=color, width=2)
        canvas.create_line(x - 3 * s, y - 6 * s, x + 6 * s, y - 6 * s, x + 6 * s, y + 4 * s, **line)
    elif name == "close":
        canvas.create_line(x - 5 * s, y - 5 * s, x + 5 * s, y + 5 * s, **line)
        canvas.create_line(x - 5 * s, y + 5 * s, x + 5 * s, y - 5 * s, **line)
    elif name == "check":
        canvas.create_line(x - 5 * s, y, x - 1 * s, y + 4 * s, x + 6 * s, y - 4 * s, **line)
    elif name == "warning":
        canvas.create_polygon(x, y - 7 * s, x + 8 * s, y + 6 * s, x - 8 * s, y + 6 * s, fill="", outline=color,
                              width=2, joinstyle="round")
        canvas.create_line(x, y - 2 * s, x, y + 2 * s, **line)
        canvas.create_oval(x - 1, y + 3.5 * s, x + 1, y + 5 * s, fill=color, outline=color)
    elif name == "host":
        canvas.create_rectangle(x - 7 * s, y - 5 * s, x + 7 * s, y + 3 * s, outline=color, width=1.5)
        canvas.create_line(x - 3 * s, y + 6 * s, x + 3 * s, y + 6 * s, fill=color, width=1.5)
    elif name == "grid":
        for dx in (-4, 4):
            for dy in (-4, 4):
                canvas.create_rectangle(x + dx * s - 3 * s, y + dy * s - 3 * s, x + dx * s + 3 * s,
                                        y + dy * s + 3 * s, outline=color, width=1.5)
    elif name == "pulse":
        canvas.create_line(x - 8 * s, y, x - 4 * s, y, x - 2 * s, y - 5 * s, x + 1 * s, y + 5 * s,
                           x + 3 * s, y, x + 8 * s, y, **line)
    elif name == "plug":
        canvas.create_rectangle(x - 9 * s, y - 6 * s, x + 9 * s, y + 8 * s, outline=color, width=2)
        canvas.create_line(x - 4 * s, y - 6 * s, x - 4 * s, y - 13 * s, **line)
        canvas.create_line(x + 4 * s, y - 6 * s, x + 4 * s, y - 13 * s, **line)
        canvas.create_line(x, y + 8 * s, x, y + 16 * s, **line)


# ------------------------------------------------------------------ wallpaper
def draw_wallpaper(canvas: tk.Canvas, width: int, height: int, top: str, bottom: str, grid: str,
                   trace: str, node: str, seed: int = 7, tags: str = "wallpaper") -> None:
    """Technical wallpaper: vertical gradient, fine grid, circuit traces and orbit rings."""
    canvas.delete(tags)
    steps = max(1, height // 3)
    for index in range(steps):
        y0 = index * height / steps
        canvas.create_rectangle(0, y0, width, y0 + height / steps + 1, fill=mix(top, bottom, index / steps),
                                outline="", tags=tags)
    for gx in range(0, width, 28):
        canvas.create_line(gx, 0, gx, height, fill=grid, tags=tags)
    for gy in range(0, height, 28):
        canvas.create_line(0, gy, width, gy, fill=grid, tags=tags)
    rng = random.Random(seed)
    for _ in range(max(6, width // 90)):
        x = rng.randrange(0, max(1, width), 28)
        y = rng.randrange(0, max(1, height), 28)
        points = [x, y]
        for _step in range(rng.randint(2, 4)):
            if rng.random() < .5:
                x += rng.choice((-1, 1)) * 28 * rng.randint(1, 4)
            else:
                y += rng.choice((-1, 1)) * 28 * rng.randint(1, 2)
            points += [x, y]
        canvas.create_line(*points, fill=trace, width=1.5, tags=tags)
        canvas.create_oval(points[0] - 3, points[1] - 3, points[0] + 3, points[1] + 3, fill=node, outline="",
                           tags=tags)
        canvas.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5, outline=node, width=1.5, tags=tags)
    cx, cy = width - 150, height * 0.55
    for radius in (60, 105, 150, 195):
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=grid, width=1, tags=tags)
    for angle in (18, 132, 250):
        rad = math.radians(angle)
        px, py = cx + 105 * math.cos(rad), cy + 105 * math.sin(rad)
        canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill=node, outline="", tags=tags)
    canvas.tag_lower(tags)

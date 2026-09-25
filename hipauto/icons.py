"""Ícones vetoriais desenhados no Canvas, nítidos em qualquer escala."""

from __future__ import annotations

import tkinter as tk


def draw_icon(canvas: tk.Canvas, category: str, color: str, x: float, y: float, fill: str) -> None:
    line = {"fill": color, "width": 2}
    box = {"fill": "", "outline": color, "width": 2}
    if category == "scale":
        canvas.create_rectangle(x - 14, y - 12, x + 14, y + 12, **box)
        canvas.create_arc(x - 8, y - 8, x + 8, y + 8, start=20, extent=140, style="arc", outline=color, width=2)
        canvas.create_line(x, y - 1, x + 5, y - 6, **line)
    elif category == "printer":
        canvas.create_rectangle(x - 12, y - 16, x + 12, y - 5, **box)
        canvas.create_rectangle(x - 16, y - 5, x + 16, y + 11, **box)
        canvas.create_rectangle(x - 10, y + 5, x + 10, y + 17, fill=fill, outline=color, width=2)
    elif category == "pinpad":
        canvas.create_rectangle(x - 13, y - 17, x + 13, y + 17, **box)
        canvas.create_rectangle(x - 8, y - 12, x + 8, y - 5, **box)
        for row in range(3):
            for col in range(3):
                cx, cy = x - 7 + col * 7, y + 1 + row * 6
                canvas.create_oval(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, fill=color, outline="")
    elif category == "keyboard":
        canvas.create_rectangle(x - 18, y - 10, x + 18, y + 10, **box)
        for row in range(2):
            for col in range(5):
                cx, cy = x - 12 + col * 6, y - 4 + row * 6
                canvas.create_rectangle(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, fill=color, outline="")
        canvas.create_line(x - 8, y + 6, x + 8, y + 6, **line)
    elif category == "scanner":
        canvas.create_polygon(x - 14, y - 12, x + 8, y - 12, x + 14, y - 4, x - 2, y - 4, x - 6, y + 16,
                              x - 14, y + 16, fill="", outline=color, width=2)
        for offset in (-8, -3, 2, 7):
            canvas.create_line(x + 16, y + offset, x + 22, y + offset, fill=color, width=1)
    elif category in {"monitor", "touchscreen"}:
        canvas.create_rectangle(x - 17, y - 13, x + 17, y + 10, **box)
        canvas.create_line(x, y + 10, x, y + 16, **line)
        canvas.create_line(x - 9, y + 16, x + 9, y + 16, **line)
        if category == "touchscreen":
            canvas.create_oval(x - 4, y - 5, x + 4, y + 3, outline=color, width=2)
    elif category == "biometric":
        for inset in (0, 5, 10):
            canvas.create_arc(x - 15 + inset, y - 17 + inset, x + 15 - inset, y + 17 - inset,
                              start=25, extent=285, style="arc", outline=color, width=2)
    else:
        canvas.create_rectangle(x - 16, y - 10, x + 10, y + 10, **box)
        canvas.create_line(x + 10, y - 5, x + 17, y - 5, x + 17, y + 5, x + 10, y + 5, **line)
        canvas.create_line(x - 11, y - 15, x - 11, y - 10, x + 5, y - 10, x + 5, y - 15, **line)


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float = 16,
                 **kwargs) -> int:
    points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2,
              x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

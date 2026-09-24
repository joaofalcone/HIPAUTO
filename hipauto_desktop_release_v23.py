#!/usr/bin/env python3
"""Entrada estável do HIPAUTO Desktop 23.0."""

import tkinter as tk

import hipauto_desktop_v23 as v23


NativeFrame = tk.Frame


class CompatibleFrame(NativeFrame):
    """Accept CSS-like vertical padding tuples on every supported Tk version."""
    def __init__(self, master=None, cnf=None, **kwargs):
        if isinstance(kwargs.get("pady"), tuple):
            kwargs["pady"] = kwargs["pady"][0]
        super().__init__(master, cnf or {}, **kwargs)


v23.tk.Frame = CompatibleFrame


if __name__ == "__main__":
    v23.HipautoDesktop().mainloop()

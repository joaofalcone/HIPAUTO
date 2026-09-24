#!/usr/bin/env python3
"""Entrada estável da versão publicada do HIPAUTO Desktop."""

import hipauto_desktop_v22 as v22


class HipautoDesktop(v22.HipautoDesktop):
    def __init__(self):
        super().__init__()
        self.title("HIPAUTO · Diagnóstico do PDV")


if __name__ == "__main__":
    HipautoDesktop().mainloop()

#!/usr/bin/env python3
"""Entrada estável do HIPAUTO Desktop.

Uso:
  hipauto_desktop.py              abre a interface
  hipauto_desktop.py --report     imprime o inventário em JSON (suporte)
  hipauto_desktop.py --report --test   inclui os testes de comunicação
"""

import json
import sys


def main(argv: list[str]) -> int:
    # A sonda SMAK roda em processo filho isolado e nunca deve abrir a interface.
    if "--smak-probe" in argv:
        from hipauto import smak
        smak.worker()
        return 0
    if "--version" in argv:
        from hipauto import __version__
        print(__version__)
        return 0
    if "--report" in argv:
        from hipauto import report
        print(json.dumps(report.build("--test" in argv), ensure_ascii=False, indent=2))
        return 0
    from hipauto.ui import HipautoDesktop
    HipautoDesktop().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

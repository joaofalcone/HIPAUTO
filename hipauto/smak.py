"""Identificação somente leitura do teclado SMAK PS/2 pela biblioteca do fabricante."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from typing import Any

from .system import ROOT, resource_path

FLAG = "--smak-probe"


def worker() -> None:
    """Runs in a child process because the vendor library accesses the i8042 directly."""
    result: dict[str, Any] = {"detected": False, "interface": -1, "status": 255}
    lib = None
    try:
        lib = ctypes.CDLL(str(resource_path("vendor/smak/libsk_access.so.64")))
        lib.Select_Interface.restype = ctypes.c_int
        interface = int(lib.Select_Interface())
        result["interface"] = interface
        if interface == 0:
            firmware = ctypes.create_string_buffer(64)
            serial = ctypes.create_string_buffer(64)
            lib.Get_Firmware_Version(firmware)
            lib.Get_Serial_Number(serial)
            lib.Get_Status.restype = ctypes.c_ubyte
            status = int(lib.Get_Status())
            fw = firmware.value.decode("latin1", "replace").strip()
            sn = serial.value.decode("latin1", "replace").strip()
            # Firmwares PS/2 antigos devolvem a versão também na chamada do serial.
            if sn == fw or (fw and sn and fw.replace("(PS2)=", "") == sn):
                sn = ""
            result.update({"detected": status == 0, "status": status, "firmware": fw, "serial": sn})
    except Exception as exc:  # a biblioteca do fabricante pode falhar de várias formas
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if lib is not None:
            try:
                lib.Free_Sk_Access()
            except Exception:
                pass
    print(json.dumps(result, ensure_ascii=False), flush=True)


def command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, FLAG]
    return [sys.executable, str(ROOT / "hipauto_desktop.py"), FLAG]


def probe(timeout: float = 12) -> dict[str, Any]:
    env = os.environ.copy()
    env.update({"SK_NOHID": "1", "SK_NOCP": "1", "SK_LOG": "0"})
    try:
        completed = subprocess.run(command(), capture_output=True, text=True, timeout=timeout,
                                   env=env, check=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"detected": False, "error": "Tempo esgotado na identificação SMAK"}
    except OSError as exc:
        return {"detected": False, "error": f"Falha na sonda SMAK: {exc}"}
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    try:
        return json.loads(lines[-1]) if lines else {"detected": False, "error": "Sonda sem resposta"}
    except ValueError:
        return {"detected": False, "error": "Resposta inválida da sonda SMAK"}

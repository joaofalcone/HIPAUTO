#!/usr/bin/env python3
"""HIPAUTO V14 - identificacao segura de teclado SMAK PS/2."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

import hipauto_v13 as v13

core = v13.core
BASE_DISCOVER = core.discover


def resource_path(relative):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / relative


def probe_smak_worker():
    """Executed in a child process because the vendor library accesses i8042 directly."""
    result = {"detected": False, "interface": -1, "status": 255}
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
            # Some older PS/2 firmware returns its version in the serial call.
            if sn == fw or (fw and sn and fw.replace("(PS2)=", "") == sn):
                sn = ""
            result.update({"detected": status == 0, "status": status,
                           "firmware": fw, "serial": sn})
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if lib is not None:
            try:
                lib.Free_Sk_Access()
            except Exception:
                pass
    print(json.dumps(result, ensure_ascii=False), flush=True)


def probe_smak(timeout=12):
    env = os.environ.copy()
    env.update({"SK_NOHID": "1", "SK_NOCP": "1", "SK_LOG": "0"})
    try:
        completed = subprocess.run(
            [sys.executable, "--smak-probe"], capture_output=True, text=True,
            timeout=timeout, env=env, check=False,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
        return json.loads(lines[-1]) if lines else {"detected": False, "error": "Sonda sem resposta"}
    except subprocess.TimeoutExpired:
        return {"detected": False, "error": "Timeout na identificação SMAK"}
    except Exception as exc:
        return {"detected": False, "error": f"Falha na sonda SMAK: {exc}"}


def discover():
    devices = BASE_DISCOVER()
    ps2 = [d for d in devices if d.get("category") == "keyboard" and d.get("connection") == "PS/2"]
    if ps2:
        probe = probe_smak()
        if probe.get("detected"):
            firmware = probe.get("firmware") or "Não informado"
            for device in ps2:
                device.update({
                    "name": "SMAK SKO-44",
                    "vendor_id": "SMAK",
                    "product_id": "SKO-44",
                    "driver": "i8042 / libsk_access",
                    "serial_number": probe.get("serial") or None,
                    "detail": f"SMAK confirmado pelo protocolo do fabricante; firmware {firmware}",
                    "recommended_port": "serio0",
                    "smak_probe": probe,
                    "confidence": {"level": "high", "label": "Alta",
                                   "reason": "Biblioteca oficial SMAK confirmou o teclado na interface PS/2"},
                })
                device.setdefault("evidence", []).append(
                    f"Sonda oficial SMAK: interface PS/2, status 0, firmware {firmware}"
                )
                details = device.setdefault("port_details", {})
                details.update({"stable": "/dev/input/by-path/platform-i8042-serio-0-event-kbd",
                                "description": "Controladora PS/2 i8042 - serio0"})
    with core.REGISTRY_LOCK:
        core.REGISTRY.clear()
        core.REGISTRY.update({item["id"]: item for item in devices})
    return devices


class Handler(v13.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json({"ok": True, "version": "14.0", "platform": "Ubuntu Desktop",
                              "smakProbe": "isolated-read-only"})
        if path == "/api/devices":
            return self.json({"devices": discover(),
                              "environment": v13.v12.v11.v10.v9.v8.v7.v6.v5.environment(),
                              "scannedAt": int(time.time())})
        return super().do_GET()


core.discover = discover
core.Handler = Handler

if __name__ == "__main__":
    if "--smak-probe" in sys.argv:
        probe_smak_worker()
    else:
        core.main()

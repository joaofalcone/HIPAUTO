#!/usr/bin/env python3
"""HIPAUTO V18 - descoberta ativa e leitura precisa de balancas seriais P05."""
import os
from pathlib import Path
import re
import select
import sys
import termios
import time
from urllib.parse import urlparse

import hipauto_v17 as v17

core = v17.core
BASE_DISCOVER = v17.v16.v15.v14.discover
BASE_TEST = core.test_device
P05_FRAME = re.compile(br"^\x02([0-9]{5}|I{5}|N{5}|S{5})\x03$")


def decode_p05(data):
    """Return protocol evidence; five numeric digits are kilograms with 3 decimals."""
    match = P05_FRAME.fullmatch(bytes(data))
    if not match:
        return None
    payload = match.group(1).decode("ascii")
    if payload.isdigit():
        value = int(payload) / 1000
        shown = f"{value:.3f}".rstrip("0").rstrip(".") or "0"
        return {"kind": "weight", "payload": payload, "weight": f"{shown} kg"}
    states = {"IIIII": "peso instável", "NNNNN": "peso negativo", "SSSSS": "sobrecarga"}
    return {"kind": "state", "payload": payload, "state": states[payload]}


def probe_p05(port, timeout=1.2):
    fd = None
    old = None
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        old = termios.tcgetattr(fd)
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[4] = attrs[5] = termios.B9600
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
        os.write(fd, b"\x05")
        end = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < end and len(data) < 64:
            ready, _, _ = select.select([fd], [], [], min(.15, max(0, end-time.monotonic())))
            if ready:
                data.extend(os.read(fd, 64-len(data)))
                if b"\x03" in data:
                    break
        decoded = decode_p05(data)
        return {"matched": bool(decoded), "bytes": list(data), "hex": bytes(data).hex(" "),
                "decoded": decoded}
    except PermissionError:
        return {"matched": False, "error": "permission-denied"}
    except OSError as exc:
        return {"matched": False, "error": str(exc)}
    finally:
        if fd is not None:
            if old is not None:
                try: termios.tcsetattr(fd, termios.TCSANOW, old)
                except OSError: pass
            os.close(fd)


def port_is_busy(port):
    code, output = core.run(["fuser", port], 1.0)
    return code == 0 and bool(output.strip())


def promote_scale(device, probe):
    decoded = probe["decoded"]
    detail = "Balança confirmada por resposta serial ao ENQ no protocolo P05"
    if decoded["kind"] == "weight":
        detail += f"; peso atual {decoded['weight']}"
    else:
        detail += f"; {decoded['state']}"
    device.update({
        "category": "scale",
        "name": "Balança serial - protocolo P05",
        "connection": "Serial",
        "driver": device.get("driver") or "serial_core",
        "detail": detail,
        "weight": decoded.get("weight"),
        "scale_protocol": "P05 compatível",
        "scale_probe": probe,
        "homologation": {"status": "unknown", "label": "Protocolo P05 identificado; modelo não informado"},
        "confidence": {"level": "high", "label": "Alta para tipo/protocolo",
                       "reason": "ENQ recebeu quadro P05 válido; fabricante e modelo não são exclusivos do protocolo"},
    })
    device.setdefault("evidence", []).append(
        f"P05: ENQ 05h -> {probe['hex']} em 9600 8N1"
    )
    details = device.setdefault("port_details", {})
    details.update({"baudrate": 9600, "data_bits": 8, "stop_bits": 1, "parity": "N",
                    "description": f"{device.get('port')} - balança serial P05 compatível"})
    return device


def discover():
    devices = BASE_DISCOVER()
    for device in devices:
        port = device.get("port")
        if not port or device.get("category") not in {"unknown", "scale"}:
            continue
        if not re.fullmatch(r"/dev/tty(?:S|USB|ACM)\d+", port) or not Path(port).exists():
            continue
        if port_is_busy(port):
            device.setdefault("evidence", []).append("Sondagem P05 ignorada: porta em uso")
            continue
        probe = probe_p05(port)
        if probe.get("matched"):
            promote_scale(device, probe)
    devices.sort(key=lambda d: ({"pinpad":0,"scanner":1,"scale":2,"printer":3,
                                 "keyboard":4,"biometric":5,"monitor":6}.get(d.get("category"),9), d.get("name", "")))
    with core.REGISTRY_LOCK:
        core.REGISTRY.clear()
        core.REGISTRY.update({item["id"]: item for item in devices})
    return devices


def test_device(device):
    if device.get("category") == "scale" and device.get("scale_protocol") == "P05 compatível":
        probe = probe_p05(device.get("port"), 2.0)
        if not probe.get("matched"):
            return {"status": "error", "detail": "NÃO OK: balança P05 não respondeu com quadro válido",
                    "test_scope": "weight-reading", "hex": probe.get("hex", "")}
        decoded = probe["decoded"]
        if decoded["kind"] == "weight":
            return {"status": "ok", "detail": "Peso real recebido da balança pelo protocolo P05",
                    "weight": decoded["weight"], "raw": decoded["payload"], "hex": probe["hex"],
                    "test_scope": "weight-reading"}
        return {"status": "warning", "detail": f"Balança respondeu: {decoded['state']}",
                "raw": decoded["payload"], "hex": probe["hex"], "test_scope": "weight-reading"}
    return BASE_TEST(device)


def report(run_tests=False):
    devices = discover(); results = {}
    if run_tests:
        for device in devices:
            try: tested = test_device(device)
            except Exception as exc: tested = {"status": "error", "detail": str(exc)}
            results[device["id"]] = tested; device.update(tested)
    legacy = v17.v16.v15.v14.v13.v12.v11.v10.v9.v8.v7.v6.v5
    environment = legacy.environment()
    return {"schemaVersion": 6, "appVersion": "18.0", "environment": environment,
            "devices": devices, "recommendations": legacy.recommendations(devices, environment),
            "testResults": results}


class Handler(v17.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json({"ok": True, "version": "18.0", "platform": "Ubuntu Desktop",
                              "scaleProbe": "P05 ENQ read-only", "smakProbe": "isolated-read-only"})
        if path == "/api/devices":
            legacy = v17.v16.v15.v14.v13.v12.v11.v10.v9.v8.v7.v6.v5
            return self.json({"devices": discover(), "environment": legacy.environment(),
                              "scannedAt": int(time.time())})
        if path == "/api/report": return self.json(report(False))
        return super().do_GET()
    def do_POST(self):
        if urlparse(self.path).path == "/api/test-all": return self.json(report(True))
        return super().do_POST()


core.discover = discover
core.test_device = test_device
core.Handler = Handler

if __name__ == "__main__":
    if "--smak-probe" in sys.argv: v17.v16.v15.v14.probe_smak_worker()
    else: core.main()

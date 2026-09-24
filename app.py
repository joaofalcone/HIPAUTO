#!/usr/bin/env python3
"""HIPAUTO - diagnosticador local de periféricos para PDV Linux."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CONFIG_PATH = Path(os.environ.get("HIPAUTO_CONFIG", ROOT / "config.json"))
TTY_PATTERN = re.compile(r"^tty(?:ACM|USB|S)\d+$")


def run(command: list[str], timeout: float = 3) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


def read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def load_config() -> dict[str, Any]:
    defaults = {
        "serial": {"baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1, "timeout": 1.2},
        "scale": {"request_hex": "05", "weight_regex": r"[-+]?\d+(?:[.,]\d+)?", "unit": "kg"},
        "pinpad": {"request_hex": "05"},
        "scanner": {"request_hex": ""},
        "biometric": {"request_hex": ""},
        "aliases": {},
    }
    try:
        supplied = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key, value in supplied.items():
            if isinstance(value, dict) and isinstance(defaults.get(key), dict):
                defaults[key].update(value)
            else:
                defaults[key] = value
    except (OSError, json.JSONDecodeError):
        pass
    return defaults


@dataclass
class Device:
    id: str
    category: str
    name: str
    connection: str
    port: str | None
    vendor_id: str | None = None
    product_id: str | None = None
    driver: str | None = None
    path: str | None = None
    status: str = "detected"
    detail: str = "Aguardando teste"
    weight: str | None = None


def classify(text: str, subsystem: str = "") -> str:
    value = text.lower()
    rules = [
        ("scale", ("scale", "balanca", "balança", "toledo", "filizola", "urano", "prix")),
        ("pinpad", ("pinpad", "ingenico", "verifone", "gertec", "stone", "pax ")),
        ("biometric", ("biometric", "fingerprint", "digital persona", "nitgen", "suprema")),
        ("printer", ("printer", "impressora", "epson", "bematech", "daruma", "elgin", "pos-58", "pos-80")),
        ("scanner", ("scanner", "barcode", "bar code", "honeywell", "datalogic", "symbol", "zebra")),
        ("keyboard", ("keyboard", "teclado", "kbd")),
    ]
    for category, words in rules:
        if any(word in value for word in words):
            return category
    if subsystem == "input":
        return "keyboard"
    return "unknown"


def udev_properties(path: str) -> dict[str, str]:
    code, output = run(["udevadm", "info", "--query=property", "--name", path])
    if code:
        return {}
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def serial_devices(config: dict[str, Any]) -> list[Device]:
    devices: list[Device] = []
    dev = Path("/dev")
    if not dev.exists():
        return devices
    aliases = config.get("aliases", {})
    for node in sorted(dev.iterdir()):
        if not TTY_PATTERN.match(node.name):
            continue
        props = udev_properties(str(node))
        model = props.get("ID_MODEL_FROM_DATABASE") or props.get("ID_MODEL", "Porta serial")
        vendor = props.get("ID_VENDOR_FROM_DATABASE") or props.get("ID_VENDOR", "")
        label = f"{vendor} {model}".strip().replace("_", " ")
        category = aliases.get(str(node)) or aliases.get(node.name) or classify(label)
        connection = "USB" if node.name.startswith(("ttyUSB", "ttyACM")) else "Serial"
        devices.append(Device(
            id=f"serial:{node.name}", category=category, name=label or node.name,
            connection=connection, port=str(node), vendor_id=props.get("ID_VENDOR_ID"),
            product_id=props.get("ID_MODEL_ID"), driver=props.get("ID_USB_DRIVER"), path=str(node),
        ))
    return devices


def input_devices() -> list[Device]:
    devices: list[Device] = []
    proc = read_text(Path("/proc/bus/input/devices"))
    for index, block in enumerate(proc.split("\n\n")):
        name_match = re.search(r'N: Name="([^"]+)"', block)
        handlers = re.search(r"H: Handlers=(.+)", block)
        if not name_match or not handlers or not any(x in handlers.group(1).split() for x in ("kbd",)):
            continue
        name = name_match.group(1)
        event = next((x for x in handlers.group(1).split() if x.startswith("event")), None)
        bus_match = re.search(r"I: Bus=([0-9a-fA-F]+)", block)
        bus = bus_match.group(1) if bus_match else ""
        connection = "PS/2" if bus in {"0011", "0005"} or "i8042" in block.lower() else "USB"
        category = classify(name, "input")
        devices.append(Device(
            id=f"input:{event or index}", category=category, name=name,
            connection=connection, port=None, path=f"/dev/input/{event}" if event else None,
            detail="Dispositivo de entrada detectado",
        ))
    return devices


def cups_printers() -> list[Device]:
    code, output = run(["lpstat", "-p"])
    if code:
        return []
    devices = []
    for line in output.splitlines():
        match = re.match(r"(?:printer|impressora)\s+(\S+)\s+(.+)", line, re.I)
        if not match:
            continue
        name, state = match.groups()
        devices.append(Device(id=f"printer:{name}", category="printer", name=name,
                              connection="USB/Rede", port=None, path=name,
                              status="ok" if "disabled" not in state.lower() else "error", detail=state))
    return devices


def discover() -> list[dict[str, Any]]:
    config = load_config()
    found = serial_devices(config) + input_devices() + cups_printers()
    unique: dict[str, Device] = {device.id: device for device in found}
    return [asdict(device) for device in unique.values()]


def serial_test(device: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    port = device.get("port")
    if not port or not Path(port).exists():
        return {"status": "error", "detail": "Porta serial não encontrada"}
    settings = config["serial"] | config.get(device.get("category"), {})
    script = ROOT / "serial_probe.py"
    command = [
        os.environ.get("PYTHON", "python3"), str(script), port,
        str(settings.get("baudrate", 9600)), str(settings.get("timeout", 1.2)),
        str(settings.get("request_hex", "")),
    ]
    code, output = run(command, float(settings.get("timeout", 1.2)) + 2)
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        result = {"status": "error", "detail": output or "Falha ao executar teste serial"}
    if device.get("category") == "scale" and result.get("raw"):
        match = re.search(config["scale"].get("weight_regex", r"[-+]?\d+(?:[.,]\d+)?"), result["raw"])
        if match:
            result["weight"] = f"{match.group(0).replace(',', '.')} {config['scale'].get('unit', 'kg')}"
            result["status"] = "ok"
            result["detail"] = "Peso recebido da balança"
    return result


def test_device(device: dict[str, Any]) -> dict[str, Any]:
    category = device.get("category")
    if device.get("port"):
        return serial_test(device, load_config())
    if category == "printer":
        code, output = run(["lpstat", "-p", device.get("path", "")])
        return {"status": "ok" if code == 0 and "disabled" not in output.lower() else "error",
                "detail": output or "Impressora não respondeu pelo CUPS"}
    path = device.get("path")
    if path and Path(path).exists():
        readable = os.access(path, os.R_OK)
        return {"status": "ok" if readable else "warning",
                "detail": "Dispositivo acessível" if readable else "Detectado; sem permissão de leitura"}
    return {"status": "error", "detail": "Dispositivo não está mais disponível"}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0].lstrip("/") or "index.html"
        return str(WEB / clean)

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json({"ok": True, "platform": os.uname().sysname if hasattr(os, "uname") else os.name})
        elif self.path == "/api/devices":
            self.send_json({"devices": discover(), "scannedAt": int(time.time())})
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/test":
            self.send_json({"error": "Rota não encontrada"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            device = json.loads(self.rfile.read(length) or b"{}")
            self.send_json(test_device(device))
        except Exception as error:
            self.send_json({"status": "error", "detail": str(error)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HIPAUTO - diagnóstico de periféricos de PDV")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"HIPAUTO disponível em http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()

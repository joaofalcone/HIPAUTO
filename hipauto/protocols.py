"""Protocolos de balança: P05 (ENQ/STX/ETX) e leitura genérica configurável."""

from __future__ import annotations

import re
from typing import Any

from .serialport import exchange, open_serial

P05_FRAME = re.compile(rb"\x02([0-9]{5}|I{5}|N{5}|S{5})\x03")
P05_STATES = {"IIIII": "peso instável", "NNNNN": "peso negativo", "SSSSS": "sobrecarga"}
P05_SETTINGS = {"baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1}


def format_weight(value: float, unit: str = "kg") -> str:
    shown = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{'0' if shown in {'', '-0'} else shown} {unit}"


def decode_p05(data: bytes | bytearray) -> dict[str, Any] | None:
    """Decode one exact P05 frame; five digits are kilograms with three decimals."""
    match = P05_FRAME.fullmatch(bytes(data))
    if not match:
        return None
    payload = match.group(1).decode("ascii")
    if payload.isdigit():
        return {"kind": "weight", "payload": payload, "weight": format_weight(int(payload) / 1000)}
    return {"kind": "state", "payload": payload, "state": P05_STATES[payload]}


def probe_p05(port: str, timeout: float = 1.2) -> dict[str, Any]:
    """Send ENQ (05h) at 9600 8N1 and validate the P05 reply. Read-only for the scale."""
    try:
        with open_serial(port, **P05_SETTINGS) as fd:
            data = exchange(fd, b"\x05", timeout, limit=64, complete=lambda buf: b"\x03" in buf)
    except PermissionError:
        return {"matched": False, "error": "permission-denied"}
    except (OSError, ValueError) as exc:
        return {"matched": False, "error": str(exc)}
    frame = data[data.rfind(b"\x02"):] if b"\x02" in data else data
    decoded = decode_p05(frame.strip(b"\r\n"))
    return {"matched": bool(decoded), "hex": data.hex(" "), "decoded": decoded}


ESCPOS_STATUS = b"\x10\x04\x01"  # DLE EOT 1: status em tempo real da impressora
ESCPOS_BAUDS = (9600, 115200, 38400, 19200)


def is_escpos_status(data: bytes) -> bool:
    """ESC/POS status byte: bits 1 and 4 fixed at 1, bit 7 fixed at 0."""
    return len(data) == 1 and (data[0] & 0x93) == 0x12


def probe_escpos(port: str, timeout: float = 0.35) -> dict[str, Any]:
    """Ask for the real-time printer status at common speeds. Prints nothing."""
    for baudrate in ESCPOS_BAUDS:
        try:
            with open_serial(port, baudrate) as fd:
                data = exchange(fd, ESCPOS_STATUS, timeout, limit=8)
        except (OSError, ValueError):
            return {"matched": False}
        if is_escpos_status(data):
            return {"matched": True, "baudrate": baudrate, "hex": data.hex(" ")}
    return {"matched": False}


def read_escpos_status(port: str, baudrate: int, timeout: float = 0.6) -> dict[str, Any]:
    """Printer (DLE EOT 1) and paper sensor (DLE EOT 4) status. Prints nothing."""
    with open_serial(port, baudrate) as fd:
        printer = exchange(fd, b"\x10\x04\x01", timeout, limit=8)
        paper = exchange(fd, b"\x10\x04\x04", timeout, limit=8)
    if not is_escpos_status(printer):
        return {"responding": False, "hex": (printer + paper).hex(" ")}
    status = {"responding": True, "offline": bool(printer[0] & 0x08), "hex": (printer + paper).hex(" ")}
    if is_escpos_status(paper):
        status.update(paper_end=bool(paper[0] & 0x60), paper_near_end=bool(paper[0] & 0x0C))
    return status


def parse_weight(raw: str, settings: dict[str, Any]) -> str | None:
    try:
        match = re.search(settings.get("weight_regex") or r"[-+]?\d+(?:[.,]\d+)?", raw)
    except re.error:
        return None
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    return format_weight(number, settings.get("unit", "kg"))


def read_generic_weight(port: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Configurable request/regex reading for scales that do not speak P05."""
    request = bytes.fromhex(str(settings.get("request_hex", "")).replace(" ", ""))
    with open_serial(port, settings.get("baudrate", 9600), settings.get("bytesize", 8),
                     settings.get("parity", "N"), settings.get("stopbits", 1)) as fd:
        data = exchange(fd, request, float(settings.get("timeout", 1.2)))
    raw = data.decode("ascii", errors="replace").strip()
    return {"data": data, "raw": raw, "weight": parse_weight(raw, settings) if data else None}

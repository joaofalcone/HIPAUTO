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

"""Acesso direto a portas seriais via termios, sem dependências externas."""

from __future__ import annotations

import os
import select
import termios
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .system import run

BAUD = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800, 9600: termios.B9600,
        19200: termios.B19200, 38400: termios.B38400, 57600: termios.B57600, 115200: termios.B115200}
BYTESIZE = {5: termios.CS5, 6: termios.CS6, 7: termios.CS7, 8: termios.CS8}


@contextmanager
def open_serial(port: str, baudrate: int = 9600, bytesize: int = 8, parity: str = "N",
                stopbits: int = 1) -> Iterator[int]:
    """Open a port in raw mode and always restore its original settings on exit."""
    speed = BAUD.get(int(baudrate))
    if speed is None:
        raise ValueError(f"velocidade {baudrate} não suportada")
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    original = None
    try:
        original = termios.tcgetattr(fd)
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | BYTESIZE.get(int(bytesize), termios.CS8)
        parity = str(parity or "N").upper()
        if parity in {"E", "O"}:
            attrs[2] |= termios.PARENB
        if parity == "O":
            attrs[2] |= termios.PARODD
        if int(stopbits) == 2:
            attrs[2] |= termios.CSTOPB
        attrs[4] = attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
        yield fd
    finally:
        if original is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, original)
            except (OSError, termios.error):
                pass
        os.close(fd)


def exchange(fd: int, request: bytes, timeout: float, limit: int = 4096,
             complete: Callable[[bytes], bool] | None = None, idle: float = 0.15) -> bytes:
    """Send a request and collect the reply until complete, idle after data, or timeout."""
    if request:
        os.write(fd, request)
    end = time.monotonic() + timeout
    data = bytearray()
    while len(data) < limit:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([fd], [], [], min(idle, remaining))
        if ready:
            chunk = os.read(fd, limit - len(data))
            if not chunk:
                break
            data.extend(chunk)
            if complete and complete(bytes(data)):
                break
        elif data and complete is None:
            break
    return bytes(data)


def port_in_use(port: str) -> bool:
    """True when another program holds the port (UUCP lock file or fuser)."""
    name = Path(port).name
    for folder in ("/var/lock", "/run/lock"):
        lock = Path(folder) / f"LCK..{name}"
        try:
            pid = int(lock.read_text().strip() or 0)
        except (OSError, ValueError):
            continue
        if pid and Path(f"/proc/{pid}").exists():
            return True
    code, output = run(["fuser", port], 1.5)
    return code == 0 and bool(output.strip())


def permission_hint() -> str:
    return "adicione o usuário ao grupo dialout (sudo usermod -aG dialout $USER) e reinicie a sessão"

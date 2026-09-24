#!/usr/bin/env python3
"""Sonda serial sem dependências externas, baseada em termios (Linux)."""

import json
import os
import select
import sys
import termios
import time

BAUDS = {
    1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800,
    9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
    57600: termios.B57600, 115200: termios.B115200,
}


def probe(port: str, baud: int, timeout: float, request_hex: str) -> dict:
    fd = None
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = BAUDS.get(baud, termios.B9600)
        attrs[5] = BAUDS.get(baud, termios.B9600)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = max(1, int(timeout * 10))
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
        if request_hex.strip():
            os.write(fd, bytes.fromhex(request_hex.replace(" ", "")))
        end = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], min(0.15, end - time.monotonic()))
            if ready:
                chunk = os.read(fd, 4096)
                data.extend(chunk)
                if chunk and len(chunk) < 4096:
                    time.sleep(0.05)
            elif data:
                break
        if data:
            return {"status": "ok", "detail": f"Resposta recebida ({len(data)} bytes)",
                    "raw": data.decode("ascii", errors="replace").strip(), "hex": data.hex(" ")}
        return {"status": "warning", "detail": "Porta abriu, mas não houve resposta"}
    except PermissionError:
        return {"status": "error", "detail": "Sem permissão. Adicione o usuário ao grupo dialout"}
    except OSError as error:
        return {"status": "error", "detail": f"Falha na porta serial: {error}"}
    finally:
        if fd is not None:
            os.close(fd)


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]), ensure_ascii=False))

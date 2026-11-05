"""Acesso ao sistema: recursos empacotados, comandos externos e configuração."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
USER_CONFIG = Path.home() / ".config" / "hipauto" / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "serial": {"baudrate": 9600, "timeout": 1.2, "bytesize": 8, "parity": "N", "stopbits": 1},
    "scale": {"request_hex": "05", "weight_regex": r"[-+]?\d+(?:[.,]\d+)?", "unit": "kg"},
    "pinpad": {"request_hex": "05"},
    "scanner": {"request_hex": ""},
    "biometric": {"request_hex": ""},
    "aliases": {},
}


def resource_path(relative: str) -> Path:
    return ROOT / relative


def system_env() -> dict[str, str]:
    """Environment for system tools, without the libraries bundled by PyInstaller."""
    env = os.environ.copy()
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if getattr(sys, "frozen", False):
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    env["LC_ALL"] = "C"
    return env


def run(command: list[str], timeout: float = 5.0) -> tuple[int, str]:
    """Run a command and return (exit code, stdout or stderr). Never raises."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                   check=False, env=system_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return completed.returncode, (completed.stdout or completed.stderr).strip()


def read(path: str | Path | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def read_bytes(path: str | Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError:
        return b""


def load_config() -> dict[str, Any]:
    """Defaults merged with the bundled config.json and ~/.config/hipauto/config.json."""
    result = copy.deepcopy(DEFAULT_CONFIG)
    for path in (resource_path("config.json"), USER_CONFIG):
        try:
            supplied = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(supplied, dict):
            continue
        for key, value in supplied.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value
    return result


def serial_settings(config: dict[str, Any], category: str | None) -> dict[str, Any]:
    settings = dict(config.get("serial", {}))
    settings.update(config.get(category or "", {}) if isinstance(config.get(category or ""), dict) else {})
    return settings

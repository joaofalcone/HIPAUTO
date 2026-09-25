"""Pré-requisitos do Ubuntu para o PDV e recomendações ao técnico."""

from __future__ import annotations

import grp
import os
import platform
import pwd
import shutil
import socket
import time
from typing import Any

from .system import run


def user_groups() -> list[str]:
    names = set()
    for gid in os.getgroups() + [os.getgid()]:
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            pass
    return sorted(names)


def configured_groups(user: str) -> list[str]:
    """Groups in /etc/group, which apply only after the next login."""
    try:
        primary = grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
    except KeyError:
        primary = None
    return sorted({g.gr_name for g in grp.getgrall() if user in g.gr_mem} | ({primary} if primary else set()))


def snapshot() -> dict[str, Any]:
    try:
        user = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        user = os.environ.get("USER", "")
    code, cups = run(["systemctl", "is-active", "cups"], 3)
    return {"hostname": socket.gethostname(), "os": platform.platform(), "kernel": platform.release(),
            "user": user, "root": os.geteuid() == 0, "groups": user_groups(),
            "configured_groups": configured_groups(user),
            "cups": cups if cups and code != 127 else "unknown",
            "tools": {name: shutil.which(name) is not None for name in ("udevadm", "lpstat", "fuser")},
            "generatedAt": int(time.time())}


def recommendations(devices: list[dict[str, Any]], env: dict[str, Any]) -> list[dict[str, str]]:
    items = []
    has_serial = any(d.get("port") for d in devices)
    if has_serial and not env.get("root") and "dialout" not in env.get("groups", []):
        if "dialout" in env.get("configured_groups", []):
            text = "O usuário já está no grupo dialout, mas é preciso sair e entrar na sessão para valer."
        else:
            text = ("Usuário fora do grupo dialout: portas seriais podem negar acesso. "
                    "Execute: sudo usermod -aG dialout $USER e reinicie a sessão.")
        items.append({"severity": "warning", "text": text})
    if env.get("cups") not in {"active", "unknown"}:
        items.append({"severity": "error", "text": "O serviço de impressão CUPS não está ativo."})
    missing = [name for name, ok in env.get("tools", {}).items() if not ok]
    if missing:
        items.append({"severity": "warning", "text": f"Ferramentas ausentes no Ubuntu: {', '.join(missing)}."})
    if any((d.get("homologation") or {}).get("status") == "not_homologated" for d in devices):
        items.append({"severity": "info", "text": "Há equipamento fora do catálogo Linux homologado."})
    return items

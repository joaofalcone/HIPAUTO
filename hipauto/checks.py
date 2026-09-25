"""Testes de comunicação entre cada periférico e o Ubuntu (sem teste funcional)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from . import protocols
from .discovery import network_reachable
from .serialport import open_serial, permission_hint, port_in_use
from .system import load_config, read, run, serial_settings


def result(status: str, detail: str, scope: str = "pc-interface", **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, "test_scope": scope, **extra}


def test_p05_scale(device: dict[str, Any]) -> dict[str, Any]:
    probe = protocols.probe_p05(device["port"], 2.0)
    if probe.get("error") == "permission-denied":
        return result("error", f"NÃO OK: sem permissão na porta da balança; {permission_hint()}", "weight-reading")
    if not probe.get("matched"):
        return result("error", "NÃO OK: balança P05 não respondeu com quadro válido", "weight-reading",
                      hex=probe.get("hex", ""), error=probe.get("error"))
    decoded = probe["decoded"]
    if decoded["kind"] == "weight":
        return result("ok", "Peso real recebido da balança pelo protocolo P05", "weight-reading",
                      weight=decoded["weight"], raw=decoded["payload"], hex=probe["hex"])
    return result("warning", f"Balança respondeu: {decoded['state']}", "weight-reading",
                  raw=decoded["payload"], hex=probe["hex"])


def test_generic_scale(device: dict[str, Any]) -> dict[str, Any]:
    settings = serial_settings(load_config(), "scale")
    try:
        reading = protocols.read_generic_weight(device["port"], settings)
    except PermissionError:
        return result("error", f"NÃO OK: sem permissão na porta da balança; {permission_hint()}", "weight-reading")
    except (OSError, ValueError) as exc:
        return result("error", f"NÃO OK: falha ao ler a balança ({exc})", "weight-reading")
    if not reading["data"]:
        return result("error", "NÃO OK: a porta abriu, mas nenhum peso foi recebido", "weight-reading")
    if reading["weight"] is None:
        return result("error", "NÃO OK: a balança respondeu, mas o peso não pôde ser interpretado",
                      "weight-reading", raw=reading["raw"], hex=reading["data"].hex(" "))
    return result("ok", "Peso real recebido da balança", "weight-reading", weight=reading["weight"],
                  raw=reading["raw"], hex=reading["data"].hex(" "))


def test_serial_link(device: dict[str, Any]) -> dict[str, Any]:
    port = device["port"]
    if port_in_use(port):
        return result("warning", "Porta presente e em uso por outro programa (ex.: sistema do PDV)")
    settings = serial_settings(load_config(), device.get("category"))
    try:
        with open_serial(port, settings.get("baudrate", 9600), settings.get("bytesize", 8),
                         settings.get("parity", "N"), settings.get("stopbits", 1)):
            pass
    except PermissionError:
        return result("error", f"NÃO OK: o Ubuntu negou acesso à porta; {permission_hint()}")
    except (OSError, ValueError) as exc:
        return result("error", f"NÃO OK: o Ubuntu não conseguiu abrir a porta ({exc})")
    return result("ok", "Comunicação com o PC OK: a porta serial abriu e aceitou a configuração")


def test_printer(device: dict[str, Any]) -> dict[str, Any]:
    queue = device.get("queue")
    code, state = run(["lpstat", "-p", queue])
    if code:
        return result("error", "NÃO OK: a fila não está acessível no CUPS")
    uri = device.get("printer_uri", "")
    if uri.startswith("usb://"):
        usb_path = device.get("usb_path")
        if usb_path and not Path(usb_path).exists():
            return result("error", "NÃO OK: a fila existe, mas a impressora USB foi desconectada")
        if not usb_path:
            return result("error", "NÃO OK: a fila existe, mas a impressora USB não está conectada")
    elif device.get("connection") == "Rede" and uri and not network_reachable(uri, 1.5):
        return result("error", "NÃO OK: a impressora de rede não respondeu")
    if "disabled" in state.lower():
        return result("warning", "O CUPS reconhece a impressora, mas a fila está desabilitada")
    return result("ok", "Comunicação com o PC OK: impressora e fila CUPS disponíveis")


def test_input(device: dict[str, Any]) -> dict[str, Any]:
    path = device.get("path")
    if not path or not Path(path).exists():
        return result("error", "NÃO OK: a interface de entrada desapareceu")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except PermissionError:
        # Leitura direta de /dev/input exige root; o dispositivo continua ativo para o sistema.
        return result("ok", "Comunicação com o PC OK: dispositivo ativo no sistema de entrada")
    except OSError as exc:
        return result("error", f"NÃO OK: falha ao abrir a interface ({exc})")
    os.close(fd)
    return result("ok", "Comunicação com o PC OK: interface de entrada abriu no Ubuntu")


def test_usb(device: dict[str, Any]) -> dict[str, Any]:
    path = Path(device.get("path") or "")
    if not device.get("path") or not path.exists():
        return result("error", "NÃO OK: o dispositivo saiu do barramento USB")
    authorized = read(path / "authorized")
    if authorized and authorized != "1":
        return result("error", "NÃO OK: dispositivo USB não autorizado pelo Ubuntu")
    if device.get("category") == "printer":
        return result("warning", "Impressora ativa no USB, mas sem fila configurada no CUPS")
    return result("ok", "Comunicação com o PC OK: dispositivo ativo no barramento USB")


def test_monitor(device: dict[str, Any]) -> dict[str, Any]:
    if read(device.get("path")) == "connected":
        return result("ok", "Comunicação com o PC OK: monitor ativo na saída de vídeo")
    return result("error", "NÃO OK: a saída de vídeo não está mais conectada")


def run_test(device: dict[str, Any]) -> dict[str, Any]:
    category, port, path = device.get("category"), device.get("port"), str(device.get("path") or "")
    if category == "monitor":
        return test_monitor(device)
    if port:
        if not Path(port).exists():
            return result("error", "NÃO OK: a porta não existe mais no Ubuntu")
        if category == "scale" and device.get("scale_protocol") == "P05":
            return test_p05_scale(device)
        if category == "scale":
            return test_generic_scale(device)
        return test_serial_link(device)
    if device.get("queue"):
        return test_printer(device)
    if path.startswith("/dev/input/"):
        return test_input(device)
    if path.startswith("/sys/bus/usb/") or path.startswith("/sys/devices/"):
        return test_usb(device)
    if device.get("connection") == "PS/2":
        return result("ok", "Comunicação com o PC OK: teclado ativo na controladora PS/2")
    return result("warning", "Detectado pelo Ubuntu; esta interface não possui teste de abertura")


def test_device(device: dict[str, Any]) -> dict[str, Any]:
    try:
        outcome = run_test(device)
    except Exception as exc:  # um periférico com defeito não pode derrubar o diagnóstico
        outcome = result("error", f"NÃO OK: falha inesperada no teste ({type(exc).__name__}: {exc})")
    outcome["tested_at"] = time.strftime("%H:%M:%S")
    return outcome

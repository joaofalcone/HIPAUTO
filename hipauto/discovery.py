"""Descoberta somente leitura dos periféricos do PDV no Ubuntu.

Fontes: portas seriais (udev), dispositivos de entrada, barramento USB, filas CUPS
e saídas de vídeo (DRM/EDID). Interfaces do mesmo equipamento USB são unificadas
pelo caminho físico no barramento, de modo que cada aparelho apareça uma única vez.
"""

from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import catalog, protocols, smak
from .serialport import port_in_use
from .system import load_config, read, read_bytes, run, serial_settings

TTY_PATTERN = re.compile(r"^tty(?:ACM|USB|S)\d+$")
USB_NODE = re.compile(r"^\d+-[\d.]+$")
IGNORED_INPUTS = ("power button", "sleep button", "video bus", "lid switch", "pc speaker",
                  "consumer control", "system control", "hda ", "hdmi/dp", "wmi hotkeys",
                  "intel hid", "virtual", "ydotool", "uinput")
PNP_VENDORS = {"AOC": "AOC", "ACR": "Acer", "AUO": "AU Optronics", "BNQ": "BenQ", "BOE": "BOE",
               "CMN": "Innolux", "DEL": "Dell", "ELO": "Elo Touch", "GSM": "LG", "HWP": "HP",
               "LEN": "Lenovo", "LGD": "LG Display", "PHL": "Philips", "SAM": "Samsung",
               "SHP": "Sharp", "VSC": "ViewSonic", "SNY": "Sony"}
SOURCE_RANK = {"serial": 0, "input": 1, "printer": 2, "usb": 3}


def new_device(**fields: Any) -> dict[str, Any]:
    device = {"id": "", "category": "unknown", "name": "", "connection": "", "port": None,
              "path": None, "vendor_id": None, "product_id": None, "serial_number": None,
              "manufacturer": None, "driver": None, "usb_node": None, "status": "detected",
              "detail": "Aguardando teste", "weight": None, "homologation": None,
              "confidence": None, "evidence": [], "stable_ports": [], "port_details": {}}
    device.update(fields)
    return device


def usb_node(sysfs: str | Path | None) -> str | None:
    """Name of the physical USB device (e.g. 1-2.3) that owns a sysfs path."""
    if not sysfs:
        return None
    try:
        parts = Path(sysfs).resolve().parts
    except OSError:
        return None
    nodes = [part for part in parts if USB_NODE.match(part)]
    return nodes[-1] if nodes else None


def natural_key(name: str) -> tuple[str, int]:
    match = re.match(r"(\D*)(\d*)", name)
    return (match.group(1), int(match.group(2) or 0)) if match else (name, 0)


def driver_name(sysfs: str | Path) -> str | None:
    link = Path(sysfs) / "driver"
    try:
        return link.resolve().name if link.exists() else None
    except OSError:
        return None


# ---------------------------------------------------------------- portas seriais
def udev_properties(node: str) -> dict[str, str]:
    code, output = run(["udevadm", "info", "--query=property", "--name", node])
    if code:
        return {}
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def uart_present(name: str) -> bool:
    """ttyS* only counts when a real UART exists; works without root."""
    kind = read(f"/sys/class/tty/{name}/type")
    if kind:
        return kind.isdigit() and int(kind) != 0
    for line in read("/proc/tty/driver/serial").splitlines():
        match = re.match(r"(\d+):\s+uart:(\S+)", line)
        if match and f"ttyS{match.group(1)}" == name:
            return match.group(2).lower() != "unknown"
    return False


def stable_ports() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for folder in (Path("/dev/serial/by-id"), Path("/dev/serial/by-path")):
        try:
            links = sorted(folder.iterdir())
        except OSError:
            continue
        for link in links:
            try:
                mapping.setdefault(str(link.resolve()), []).append(str(link))
            except OSError:
                pass
    return mapping


def serial_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    aliases = config.get("aliases") or {}
    try:
        nodes = [node for node in Path("/dev").iterdir() if TTY_PATTERN.match(node.name)]
    except OSError:
        return result
    for node in sorted(nodes, key=lambda item: natural_key(item.name)):
        if node.name.startswith("ttyS") and not uart_present(node.name):
            continue
        props = udev_properties(str(node))
        vid = (props.get("ID_VENDOR_ID") or "").lower() or None
        pid = (props.get("ID_MODEL_ID") or "").lower() or None
        known = catalog.known_usb(vid, pid)
        vendor = props.get("ID_VENDOR_FROM_DATABASE") or props.get("ID_VENDOR", "")
        model = props.get("ID_MODEL_FROM_DATABASE") or props.get("ID_MODEL", "")
        label = known[1] if known else " ".join(f"{vendor} {model}".replace("_", " ").split())
        category = (aliases.get(str(node)) or aliases.get(node.name)
                    or (known[0] if known else catalog.classify(label)))
        if category == "unknown" and vid:
            category = catalog.VENDOR_HINTS.get(vid, "unknown")
        usb = node.name.startswith(("ttyUSB", "ttyACM"))
        result.append(new_device(
            id=f"serial:{node.name}", source="serial", category=category,
            name=label or ("Adaptador serial USB" if usb else f"Porta serial {node.name}"),
            connection="USB-Serial" if usb else "Serial RS-232", port=str(node), path=str(node),
            vendor_id=vid, product_id=pid, serial_number=props.get("ID_SERIAL_SHORT"),
            manufacturer=vendor.replace("_", " ") or None,
            driver=props.get("ID_USB_DRIVER") or driver_name(f"/sys/class/tty/{node.name}/device"),
            usb_node=usb_node(f"/sys/class/tty/{node.name}/device") if usb else None))
    return result


# ------------------------------------------------------- dispositivos de entrada
def input_devices() -> list[dict[str, Any]]:
    result = []
    for index, block in enumerate(read("/proc/bus/input/devices").split("\n\n")):
        name_match = re.search(r'N: Name="([^"]*)"', block)
        handlers_match = re.search(r"H: Handlers=(.+)", block)
        if not name_match or not handlers_match:
            continue
        name, handlers = name_match.group(1).strip(), handlers_match.group(1).split()
        lowered = name.lower()
        if not name or any(word in lowered for word in IGNORED_INPUTS):
            continue
        identity = re.search(r"I: Bus=([0-9a-fA-F]+) Vendor=([0-9a-fA-F]+) Product=([0-9a-fA-F]+)", block)
        bus, vid, pid = (value.lower() for value in identity.groups()) if identity else ("", "", "")
        if bus == "0019":  # botões da própria placa-mãe
            continue
        is_usb = bus == "0003"
        vid, pid = (vid, pid) if is_usb else (None, None)
        known = catalog.known_usb(vid, pid)
        category = known[0] if known else catalog.classify(name)
        if category == "unknown" and is_usb:
            category = catalog.VENDOR_HINTS.get(vid or "", "unknown")
        if category == "unknown" and "kbd" in handlers:
            category = "keyboard"
        if category not in {"keyboard", "scanner", "touchscreen", "biometric"}:
            continue
        event = next((item for item in handlers if item.startswith("event")), None)
        connection = {"0011": "PS/2", "0003": "USB", "0005": "Bluetooth"}.get(bus, "Interno")
        if "i8042" in block.lower():
            connection = "PS/2"
        sysfs = re.search(r"S: Sysfs=(\S+)", block)
        result.append(new_device(
            id=f"input:{event or index}", source="input", category=category,
            name=known[1] if known else name, connection=connection,
            path=f"/dev/input/{event}" if event else None, vendor_id=vid, product_id=pid,
            driver="i8042" if connection == "PS/2" else ("usbhid" if is_usb else None),
            usb_node=usb_node(f"/sys{sysfs.group(1)}") if is_usb and sysfs else None,
            detail="Dispositivo de entrada detectado"))
    return result


# ------------------------------------------------------------------ barramento USB
def usb_devices() -> list[dict[str, Any]]:
    result = []
    root = Path("/sys/bus/usb/devices")
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return result
    for path in entries:
        if not USB_NODE.match(path.name):
            continue
        vid, pid = read(path / "idVendor").lower(), read(path / "idProduct").lower()
        if not vid or not pid or vid == "1d6b" or read(path / "bDeviceClass") == "09":
            continue
        manufacturer, product = read(path / "manufacturer"), read(path / "product")
        name = " ".join(value for value in (manufacturer, product) if value) or f"Dispositivo USB {vid}:{pid}"
        interfaces = sorted(path.glob(f"{path.name}:*"))
        classes = {read(item / "bInterfaceClass") for item in interfaces}
        drivers = [name for item in interfaces if (name := driver_name(item))]
        known = catalog.known_usb(vid, pid)
        category = (known[0] if known else catalog.VENDOR_HINTS.get(vid)
                    or ("printer" if "07" in classes else catalog.classify(name)))
        if category == "unknown":
            continue
        result.append(new_device(
            id=f"usb:{path.name}", source="usb", category=category, name=known[1] if known else name,
            connection="USB", path=str(path), vendor_id=vid, product_id=pid,
            serial_number=read(path / "serial") or None, manufacturer=manufacturer or None, product=product,
            driver=drivers[0] if drivers else None, usb_node=path.name,
            detail="Detectado diretamente no barramento USB"))
    return result


# ----------------------------------------------------------------------- CUPS
def printer_uris() -> dict[str, str]:
    code, output = run(["lpstat", "-v"])
    if code:
        return {}
    return {m.group(1): m.group(2).strip() for line in output.splitlines()
            if (m := re.match(r"device for (\S+?):\s+(.+)", line))}


def network_reachable(uri: str, timeout: float = 0.7) -> bool:
    parsed = urlparse(uri)
    if not parsed.hostname:
        return False
    default = {"ipp": 631, "ipps": 631, "http": 80, "https": 443, "socket": 9100, "lpd": 515}
    try:
        with socket.create_connection((parsed.hostname, parsed.port or default.get(parsed.scheme, 9100)),
                                      timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def cups_queues() -> list[dict[str, Any]]:
    code, states = run(["lpstat", "-p"])
    if code:
        return []
    uris = printer_uris()
    result = []
    for line in states.splitlines():
        match = re.match(r"printer\s+(\S+)\s+(.+)", line)
        if not match:
            continue
        queue, state = match.groups()
        uri = uris.get(queue, "")
        local = uri.startswith(("usb://", "serial:", "parallel:"))
        device = new_device(id=f"printer:{queue}", source="printer", category="printer", name=queue,
                            connection="USB" if uri.startswith("usb://") else ("Local" if local else "Rede"),
                            path=queue, queue=queue, printer_uri=uri, detail=f"Fila CUPS: {state.strip()}")
        if "disabled" in state.lower():
            device.update(status="warning", detail="Fila CUPS desabilitada")
        if device["connection"] == "Rede" and uri and not network_reachable(uri):
            device.update(status="error", detail="Impressora de rede não responde no endereço configurado")
        result.append(device)
    return result


def usb_uri_details(uri: str) -> tuple[str, str | None]:
    parsed = urlparse(uri)
    serial = parse_qs(parsed.query).get("serial", [None])[0]
    return catalog.norm(unquote(f"{parsed.netloc}{parsed.path}")), serial


def attach_usb_printers(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Link each USB CUPS queue to its physical printer so it is listed only once."""
    physical = [d for d in devices if d["category"] == "printer" and d.get("source") != "printer"
                and d.get("connection") == "USB"]
    used: set[str] = set()
    for queue in (d for d in devices if d.get("source") == "printer" and d["connection"] == "USB"):
        text, serial = usb_uri_details(queue.get("printer_uri", ""))
        free = [p for p in physical if p["id"] not in used]
        match = next((p for p in free if serial and p.get("serial_number") == serial), None)
        match = match or next((p for p in free if any(
            key and key in text for key in (catalog.norm(p.get("name")), catalog.norm(p.get("product"))))), None)
        if not match and len(free) == 1 and len(physical) == 1:
            match = free[0]
        if not match:
            queue.update(status="error", detail="Fila USB existe, mas a impressora não está conectada")
            continue
        used.add(match["id"])
        for key in ("vendor_id", "product_id", "serial_number", "manufacturer", "driver", "usb_node"):
            queue[key] = queue.get(key) or match.get(key)
        queue["usb_path"] = match.get("path")
        queue["name"] = f"{match['name']} (fila {queue['queue']})"
    return [d for d in devices if d["id"] not in used]


# ------------------------------------------------------------------ monitores
def parse_edid(data: bytes) -> dict[str, Any]:
    if len(data) < 128 or data[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return {}
    code = (data[8] << 8) | data[9]
    pnp = "".join(chr(((code >> shift) & 0x1F) + 64) for shift in (10, 5, 0))
    info: dict[str, Any] = {"pnp": pnp, "manufacturer": PNP_VENDORS.get(pnp, pnp),
                            "product_code": f"{data[10] | (data[11] << 8):04x}"}
    number = int.from_bytes(data[12:16], "little")
    if number:
        info["serial"] = str(number)
    for offset in range(54, 126, 18):
        block = data[offset:offset + 18]
        if block[0:2] == b"\x00\x00" and block[3] in (0xFC, 0xFF):
            text = block[5:18].split(b"\x0a")[0].decode("ascii", "replace").strip()
            if text:
                info["model" if block[3] == 0xFC else "serial"] = text
    return info


def monitor_connection(connector: str) -> str:
    name = connector.upper()
    for token, label in (("HDMI", "HDMI"), ("DP", "DisplayPort"), ("VGA", "VGA"), ("DVI", "DVI"),
                         ("EDP", "Tela interna (eDP)"), ("LVDS", "Tela interna (LVDS)")):
        if name.startswith(token) or f"-{token}" in name:
            return label
    return "Vídeo"


def monitors() -> list[dict[str, Any]]:
    connectors = []
    for status in Path("/sys/class/drm").glob("card*-*/status"):
        if read(status) == "connected":
            connectors.append((status.parent.name.split("-", 1)[1], status))
    result = []
    for index, (connector, status) in enumerate(sorted(connectors), 1):
        edid = parse_edid(read_bytes(status.parent / "edid"))
        model = " ".join(v for v in (edid.get("manufacturer"), edid.get("model")) if v)
        result.append(new_device(
            id=f"monitor:{connector}", source="drm", category="monitor",
            name=model or f"Monitor {index}", connection=monitor_connection(connector),
            path=str(status), port_name=connector, manufacturer=edid.get("manufacturer"),
            serial_number=edid.get("serial"), driver="drm", edid=edid or None,
            detail=f"Monitor conectado na saída {connector}"))
    return result


# ------------------------------------------------------------------- unificação
def identity_keys(device: dict[str, Any]) -> list[str]:
    keys = []
    if device.get("usb_node"):
        keys.append(f"node:{device['usb_node']}")
    if device.get("vendor_id") and device.get("product_id"):
        keys.append(f"id:{device['vendor_id']}:{device['product_id']}:{device.get('serial_number') or ''}")
    return keys


def merge_interfaces(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one entry per physical USB device, preferring serial > input > USB."""
    owners: dict[str, dict[str, Any]] = {}
    result = []
    for device in sorted(devices, key=lambda d: SOURCE_RANK.get(d.get("source"), 9)):
        keys = identity_keys(device)
        owner = next((owners[key] for key in keys if key in owners), None)
        if owner is None:
            result.append(device)
            owner = device
        else:
            for field in ("serial_number", "manufacturer", "driver", "vendor_id", "product_id", "usb_node"):
                owner[field] = owner.get(field) or device.get(field)
            if owner.get("category") == "unknown":
                owner["category"] = device.get("category", "unknown")
            owner.setdefault("interfaces", []).append(device.get("path") or device["id"])
        for key in keys:
            owners.setdefault(key, owner)
    return result


def confidence(device: dict[str, Any]) -> dict[str, str]:
    if device.get("vendor_id") and device.get("product_id") and device.get("serial_number"):
        return {"level": "high", "label": "Alta", "reason": "VID, PID e número de série confirmados"}
    if device.get("category") == "monitor" and device.get("edid"):
        return {"level": "high", "label": "Alta", "reason": "Identificação lida do EDID do monitor"}
    if device.get("vendor_id") and device.get("product_id"):
        return {"level": "medium", "label": "Média", "reason": "VID e PID confirmados; sem número de série"}
    if device.get("port") or device.get("path"):
        return {"level": "medium", "label": "Média", "reason": "Interface Linux confirmada; modelo sem identidade USB"}
    return {"level": "low", "label": "Baixa", "reason": "Identificação baseada somente no nome"}


def enrich(device: dict[str, Any], ports: dict[str, list[str]], config: dict[str, Any]) -> None:
    port = device.get("port")
    device["stable_ports"] = ports.get(port or "", [])
    device["recommended_port"] = (device["stable_ports"] or [port])[0] if port else device.get("port_name")
    device["port_name"] = device.get("port_name") or (Path(port).name if port else device.get("queue"))
    evidence = device["evidence"]
    if device.get("vendor_id"):
        evidence.append(f"USB {device['vendor_id']}:{device['product_id']}")
    if port:
        evidence.append(f"Porta {port}")
    if device["stable_ports"]:
        evidence.append(f"Porta estável {device['stable_ports'][0]}")
    if device.get("driver"):
        evidence.append(f"Driver {device['driver']}")
    if device.get("printer_uri"):
        evidence.append(f"CUPS {device['printer_uri']}")
    if device.get("interfaces"):
        evidence.append(f"Interfaces unificadas: {', '.join(device['interfaces'])}")
    if port:
        settings = serial_settings(config, device.get("category"))
        device["port_details"] = {"baudrate": settings.get("baudrate"), "data_bits": settings.get("bytesize"),
                                  "stop_bits": settings.get("stopbits"), "parity": settings.get("parity")}


def identify_scales(devices: list[dict[str, Any]]) -> None:
    for device in devices:
        port = device.get("port")
        if not port or device.get("category") not in {"unknown", "scale"}:
            continue
        if port_in_use(port):
            device["evidence"].append("Sondagem P05 ignorada: porta em uso por outro programa")
            continue
        probe = protocols.probe_p05(port)
        if not probe.get("matched"):
            if probe.get("error") == "permission-denied":
                device["evidence"].append("Sondagem P05 sem permissão na porta (grupo dialout)")
            continue
        decoded = probe["decoded"]
        state = f"peso atual {decoded['weight']}" if decoded["kind"] == "weight" else decoded["state"]
        device.update({
            "category": "scale", "name": "Balança serial - protocolo P05", "scale_protocol": "P05",
            "detail": f"Balança confirmada por resposta ao ENQ no protocolo P05; {state}",
            "weight": decoded.get("weight"),
            "homologation": {"status": "unknown", "label": "Protocolo P05 identificado; modelo não informado"},
            "confidence": {"level": "high", "label": "Alta para tipo/protocolo",
                           "reason": "ENQ recebeu quadro P05 válido; o protocolo não identifica o fabricante"},
            "port_details": dict(protocols.P05_SETTINGS),
        })
        device["evidence"].append(f"P05: ENQ 05h -> {probe['hex']} em 9600 8N1")


def identify_smak(devices: list[dict[str, Any]]) -> None:
    ps2 = [d for d in devices if d["category"] == "keyboard" and d["connection"] == "PS/2"]
    if not ps2:
        return
    result = smak.probe()
    if not result.get("detected"):
        return
    firmware = result.get("firmware") or "não informado"
    for device in ps2:
        device.update({
            "name": "SMAK SKO-44", "manufacturer": "SMAK", "driver": "i8042 / libsk_access",
            "serial_number": result.get("serial") or None, "firmware": result.get("firmware"),
            "detail": f"SMAK confirmado pelo protocolo do fabricante; firmware {firmware}",
            "recommended_port": "serio0",
            "confidence": {"level": "high", "label": "Alta",
                           "reason": "Biblioteca oficial SMAK confirmou o teclado na interface PS/2"},
        })
        device["evidence"].append(f"Sonda oficial SMAK: interface PS/2, status 0, firmware {firmware}")


def discover() -> list[dict[str, Any]]:
    config = load_config()
    found = serial_devices(config) + input_devices() + usb_devices()
    devices = attach_usb_printers(merge_interfaces(found) + cups_queues()) + monitors()
    ports = stable_ports()
    for device in devices:
        enrich(device, ports, config)
    identify_scales(devices)
    identify_smak(devices)
    for device in devices:
        device["confidence"] = device.get("confidence") or confidence(device)
        device["homologation"] = device.get("homologation") or catalog.homologation(
            device["category"], f"{device.get('manufacturer') or ''} {device['name']}",
            device.get("vendor_id"), device.get("product_id"))
    devices.sort(key=catalog.sort_key)
    return devices

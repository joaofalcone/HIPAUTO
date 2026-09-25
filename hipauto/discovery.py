"""Descoberta somente leitura dos periféricos do PDV no Ubuntu.

Fontes: portas seriais (udev), dispositivos de entrada, barramento USB, filas CUPS
e saídas de vídeo (DRM/EDID). Interfaces do mesmo equipamento USB são unificadas
pelo caminho físico no barramento, de modo que cada aparelho apareça uma única vez.
"""

from __future__ import annotations

import re
import socket
from concurrent.futures import ThreadPoolExecutor
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
LAST_ERRORS: list[str] = []  # fontes que falharam na última descoberta
INPUT_CATEGORIES = {"keyboard", "scanner", "touchscreen", "biometric", "card_reader"}
USB_CLASS_CATEGORY = {"07": "printer", "0b": "card_reader"}


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
    aliases = config.get("aliases") or {}
    try:
        nodes = [node for node in Path("/dev").iterdir() if TTY_PATTERN.match(node.name)]
    except OSError:
        return []
    nodes = [node for node in nodes if not node.name.startswith("ttyS") or uart_present(node.name)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        props_list = list(pool.map(lambda node: udev_properties(str(node)), nodes))
    result = []
    for node, props in sorted(zip(nodes, props_list), key=lambda item: natural_key(item[0].name)):
        vid = (props.get("ID_VENDOR_ID") or "").lower() or None
        pid = (props.get("ID_MODEL_ID") or "").lower() or None
        identity = catalog.usb_identity(vid, pid)
        usb = node.name.startswith(("ttyUSB", "ttyACM"))
        vendor = identity.get("manufacturer") or (props.get("ID_VENDOR_FROM_DATABASE")
                                                  or props.get("ID_VENDOR", "")).replace("_", " ")
        model = identity.get("model") or (props.get("ID_MODEL_FROM_DATABASE")
                                          or props.get("ID_MODEL", "")).replace("_", " ")
        adapter = identity.get("adapter", False)
        if adapter:
            label = f"Porta USB-serial ({catalog.display_name(vendor, model)})"
        else:
            label = identity.get("name") or catalog.display_name(vendor, model)
        category = (aliases.get(str(node)) or aliases.get(node.name)
                    or (None if adapter else identity.get("category"))
                    or ("unknown" if adapter else catalog.classify(label)))
        result.append(new_device(
            id=f"serial:{node.name}", source="serial", category=category,
            name=label or ("Adaptador USB-serial" if usb else f"Porta serial {node.name}"),
            connection="USB-Serial" if usb else "Serial RS-232", port=str(node), path=str(node),
            vendor_id=vid, product_id=pid, serial_number=props.get("ID_SERIAL_SHORT"),
            manufacturer=None if adapter else (vendor or None), model=None if adapter else (model or None),
            adapter=catalog.display_name(vendor, model) if adapter else None,
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
        identity = catalog.usb_identity(vid, pid)
        category = catalog.classify(name)
        if category == "unknown":
            category = identity.get("category") or "unknown"
        if category == "unknown" and "kbd" in handlers:
            category = "keyboard"
        if category not in INPUT_CATEGORIES:
            continue
        event = next((item for item in handlers if item.startswith("event")), None)
        connection = {"0011": "PS/2", "0003": "USB", "0005": "Bluetooth"}.get(bus, "Interno")
        if "i8042" in block.lower():
            connection = "PS/2"
        sysfs = re.search(r"S: Sysfs=(\S+)", block)
        result.append(new_device(
            id=f"input:{event or index}", source="input", category=category,
            name=identity.get("name") or name, connection=connection,
            manufacturer=identity.get("manufacturer"), model=identity.get("model"),
            path=f"/dev/input/{event}" if event else None, vendor_id=vid, product_id=pid,
            driver="i8042" if connection == "PS/2" else ("usbhid" if is_usb else None),
            usb_node=usb_node(f"/sys{sysfs.group(1)}") if is_usb and sysfs else None,
            detail="Dispositivo de entrada detectado"))
    return result


# ------------------------------------------------------------------ barramento USB
def parse_ieee1284(text: str) -> dict[str, str]:
    """Printer self-identification, e.g. 'MFG:EPSON;CMD:ESC/POS;MDL:TM-T20;'."""
    fields = {}
    for part in text.split(";"):
        key, _, value = part.partition(":")
        if value.strip():
            fields[key.strip().upper()] = value.strip()
    return {"manufacturer": fields.get("MFG") or fields.get("MANUFACTURER"),
            "model": fields.get("MDL") or fields.get("MODEL"),
            "commands": fields.get("CMD") or fields.get("COMMAND SET")}


def usb_devices() -> list[dict[str, Any]]:
    result = []
    try:
        entries = sorted(Path("/sys/bus/usb/devices").iterdir(), key=lambda item: item.name)
    except OSError:
        return result
    for path in entries:
        if not USB_NODE.match(path.name):
            continue
        vid, pid = read(path / "idVendor").lower(), read(path / "idProduct").lower()
        if not vid or not pid or vid == "1d6b" or read(path / "bDeviceClass") == "09":
            continue
        interfaces = sorted(path.glob(f"{path.name}:*"))
        classes = {read(item / "bInterfaceClass") for item in interfaces}
        drivers = [name for item in interfaces if (name := driver_name(item))]
        ieee = next((parse_ieee1284(text) for item in interfaces
                     if (text := read(item / "ieee1284_id"))), {})
        identity = catalog.usb_identity(vid, pid)
        descriptor_maker, product = read(path / "manufacturer"), read(path / "product")
        manufacturer = ieee.get("manufacturer") or identity.get("manufacturer") or descriptor_maker
        model = ieee.get("model") or product or identity.get("model")
        name = identity.get("name") or catalog.display_name(manufacturer, model) or f"Dispositivo USB {vid}:{pid}"
        category = (identity.get("category") or next((USB_CLASS_CATEGORY[c] for c in sorted(classes)
                                                      if c in USB_CLASS_CATEGORY), None)
                    or catalog.classify(f"{descriptor_maker} {product}"))
        if identity.get("adapter") or category == "unknown":
            continue
        evidence = [f"IEEE 1284: {ieee['manufacturer']} {ieee['model']}"] if ieee.get("model") else []
        result.append(new_device(
            id=f"usb:{path.name}", source="usb", category=category, name=name, connection="USB",
            path=str(path), vendor_id=vid, product_id=pid, serial_number=read(path / "serial") or None,
            manufacturer=manufacturer or None, model=model or None, product=product,
            commands=ieee.get("commands"), usb_speed=read(path / "speed") or None,
            driver=drivers[0] if drivers else None, usb_node=path.name, evidence=evidence,
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
        result.append(device)
    network = [d for d in result if d["connection"] == "Rede" and d["printer_uri"]]
    if network:
        with ThreadPoolExecutor(max_workers=8) as pool:
            online = list(pool.map(lambda d: network_reachable(d["printer_uri"]), network))
        for device, ok in zip(network, online):
            if not ok:
                device.update(status="error", detail="Impressora de rede não responde no endereço configurado")
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
    width_cm, height_cm = data[21], data[22]
    if width_cm and height_cm:
        info["diagonal"] = round((width_cm ** 2 + height_cm ** 2) ** 0.5 / 2.54, 1)
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
        modes = read(status.parent / "modes").splitlines()
        model = catalog.display_name(edid.get("manufacturer"), edid.get("model"))
        details = ", ".join(filter(None, [modes[0] if modes else None,
                                          f"{edid['diagonal']}\"" if edid.get("diagonal") else None]))
        result.append(new_device(
            id=f"monitor:{connector}", source="drm", category="monitor",
            name=model or f"Monitor {index}", connection=monitor_connection(connector),
            path=str(status), port_name=connector, manufacturer=edid.get("manufacturer"),
            model=edid.get("model"), serial_number=edid.get("serial"), driver="drm", edid=edid or None,
            resolution=modes[0] if modes else None, diagonal=edid.get("diagonal"),
            detail=f"Monitor conectado na saída {connector}" + (f" ({details})" if details else "")))
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
        # Com nó físico conhecido só o nó decide: aparelhos idênticos em portas
        # diferentes (mesmo VID/PID, sem número de série) continuam separados.
        lookup = keys[:1] if device.get("usb_node") else keys
        owner = next((owners[key] for key in lookup if key in owners), None)
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


def probe_serial_port(device: dict[str, Any]) -> None:
    """Identify what is attached to an unknown serial port (scale P05, ESC/POS printer)."""
    port = device["port"]
    if port_in_use(port):
        device["evidence"].append("Sondagem ignorada: porta em uso por outro programa")
        return
    probe = protocols.probe_p05(port)
    if probe.get("error") == "permission-denied":
        device["evidence"].append("Sondagem sem permissão na porta (grupo dialout)")
        return
    if probe.get("matched"):
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
        return
    if device.get("category") != "unknown":
        return
    printer = protocols.probe_escpos(port)
    if printer.get("matched"):
        device.update({
            "category": "printer", "name": "Impressora serial ESC/POS", "printer_protocol": "ESC/POS",
            "detail": f"Impressora confirmada pelo status em tempo real ESC/POS a {printer['baudrate']} bps",
            "confidence": {"level": "high", "label": "Alta para tipo/protocolo",
                           "reason": "DLE EOT 1 retornou byte de status ESC/POS válido"},
            "port_details": {"baudrate": printer["baudrate"], "data_bits": 8, "stop_bits": 1, "parity": "N"},
        })
        device["evidence"].append(f"ESC/POS: DLE EOT 1 -> {printer['hex']} a {printer['baudrate']} bps")


def identify_serial(devices: list[dict[str, Any]]) -> None:
    targets = [d for d in devices if d.get("port") and d.get("category") in {"unknown", "scale"}]
    if targets:
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
            list(pool.map(probe_serial_port, targets))


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


def safe(source: Any, errors: list[str], *args: Any) -> list[dict[str, Any]]:
    """Run one discovery source; a broken source never hides the others."""
    try:
        return source(*args)
    except Exception as exc:  # isolamento por fonte
        errors.append(f"{getattr(source, '__name__', 'fonte')}: {type(exc).__name__}: {exc}")
        return []


def discover() -> list[dict[str, Any]]:
    config = load_config()
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {name: pool.submit(safe, source, errors, *args) for name, source, args in (
            ("serial", serial_devices, (config,)), ("input", input_devices, ()), ("usb", usb_devices, ()),
            ("cups", cups_queues, ()), ("monitors", monitors, ()), ("ports", stable_ports_list, ()))}
        results = {name: job.result() for name, job in jobs.items()}
    found = results["serial"] + results["input"] + results["usb"]
    devices = attach_usb_printers(merge_interfaces(found) + results["cups"]) + results["monitors"]
    ports = dict(results["ports"])
    for device in devices:
        enrich(device, ports, config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        serial_job = pool.submit(safe, identify_serial, errors, devices)
        smak_job = pool.submit(safe, identify_smak, errors, devices)
        serial_job.result()
        smak_job.result()
    for device in devices:
        device["confidence"] = device.get("confidence") or confidence(device)
        device["homologation"] = device.get("homologation") or catalog.homologation(
            device["category"], f"{device.get('manufacturer') or ''} {device['name']} {device.get('model') or ''}",
            device.get("vendor_id"), device.get("product_id"))
    devices.sort(key=catalog.sort_key)
    LAST_ERRORS[:] = errors
    return devices


def stable_ports_list() -> list[tuple[str, list[str]]]:
    return list(stable_ports().items())

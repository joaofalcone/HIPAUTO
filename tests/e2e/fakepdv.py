#!/usr/bin/env python3
"""PDV simulado para testes de ponta a ponta (roda como root dentro de um container).

Cria um /sys, /proc/bus/input/devices e /dev falsos com periféricos de PDV, comandos
falsos (udevadm, lpstat, fuser, systemctl) e emuladores em pty que respondem de verdade
pelos protocolos P05 (balança) e ESC/POS (impressora). O estado dos emuladores é
controlado por arquivos em /run/fakepdv (ex.: echo IIIII > /run/fakepdv/scale).

Controles (arquivos em /run/fakepdv, graváveis pelo usuário de teste):
  scale       peso P05 de 5 dígitos, IIIII/NNNNN/SSSSS ou off
  printer     ok, nopaper, offline ou off
  cups        idle ou disabled (fila TM-T20)
  busy        portas em uso por outro programa (uma por linha)
  unplugged   periféricos desconectados (ex.: ttyACM0)

Uso: fakepdv.py setup   (monta tudo e deixa os emuladores rodando)
"""

import json
import os
import pty
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

FAKE = Path("/opt/fakepdv")
CONTROL = Path("/run/fakepdv")
PCI = "/sys/devices/pci0000:00/0000:00:14.0/usb1"

USB = {  # nó USB: (vid, pid, fabricante, produto, serial, [(interface, classe, driver, ieee1284)])
    "1-1": ("04b8", "0e03", "EPSON", "TM-T20", "X1", [("1-1:1.0", "07", "usblp",
                                                     "MFG:EPSON;CMD:ESC/POS;MDL:TM-T20;CLS:PRINTER;")]),
    "1-2": ("0c2e", "0b81", "Honeywell Imaging & Mobility", "Voyager 1400g", "", [("1-2:1.0", "03", "usbhid", "")]),
    "1-3": ("067b", "2303", "Prolific Technology Inc.", "USB-Serial Controller", "", [("1-3:1.0", "ff", "pl2303", "")]),
    "1-4": ("1753", "c902", "GERTEC", "PPC930", "PP123", [("1-4:1.0", "02", "cdc_acm", "")]),
    "1-6": ("2fe7", "0001", "ELGIN", "SMART SAT", "S0001", [("1-6:1.0", "02", "cdc_acm", "")]),
    "1-7": ("0d3a", "0206", "Posiflex", "Cash Drawer", "", [("1-7:1.0", "03", "usbhid", "")]),
    "1-8": ("0951", "1666", "Kingston", "DataTraveler 3.0", "K1", [("1-8:1.0", "08", "usb-storage", "")]),
}
TTYS = {  # nó: (usb ou None, propriedades udev, uart type)
    "ttyS0": (None, {}, "4"),
    "ttyS1": (None, {}, "4"),
    "ttyS2": (None, {}, "0"),  # porta sem UART real: deve ser ignorada
    "ttyACM0": ("1-4", {"ID_VENDOR_ID": "1753", "ID_MODEL_ID": "c902", "ID_VENDOR": "GERTEC", "ID_MODEL": "PPC930",
                        "ID_SERIAL_SHORT": "PP123", "ID_USB_DRIVER": "cdc_acm"}, None),
    "ttyUSB0": ("1-3", {"ID_VENDOR_ID": "067b", "ID_MODEL_ID": "2303", "ID_VENDOR": "Prolific_Technology_Inc.",
                        "ID_MODEL": "USB-Serial_Controller", "ID_USB_DRIVER": "pl2303"}, None),
}
INPUT = """I: Bus=0019 Vendor=0000 Product=0001 Version=0000
N: Name="Power Button"
H: Handlers=kbd event1
S: Sysfs=/devices/LNXSYSTM:00/input/input1

I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
P: Phys=isa0060/serio0/input0
S: Sysfs=/devices/platform/i8042/serio0/input/input0
H: Handlers=sysrq kbd event0 leds

I: Bus=0003 Vendor=0c2e Product=0b81 Version=0111
N: Name="Honeywell Imaging & Mobility 1400g"
S: Sysfs=/devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2:1.0/0003:0C2E:0B81.0001/input/input5
H: Handlers=sysrq kbd event5 leds

I: Bus=0003 Vendor=046d Product=c077 Version=0111
N: Name="Logitech USB Optical Mouse"
S: Sysfs=/devices/pci0000:00/0000:00:14.0/usb1/1-5/1-5:1.0/input/input7
H: Handlers=mouse0 event7
"""


def write(path, content, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    path.chmod(mode)


def link(path, target):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    path.symlink_to(target)


def edid():
    data = bytearray(128)
    data[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
    code = ((ord("S") - 64) << 10) | ((ord("A") - 64) << 5) | (ord("M") - 64)
    data[8], data[9] = code >> 8, code & 0xFF
    data[10], data[11] = 0x2D, 0x0D
    data[12:16] = (123456).to_bytes(4, "little")
    data[21], data[22] = 53, 30
    data[54:59] = b"\x00\x00\x00\xfc\x00"
    data[59:72] = b"S24F350\n     "
    return bytes(data)


def build_sys():
    subprocess.run(["mount", "-t", "tmpfs", "fakesys", "/sys"], check=True)
    for node, (vid, pid, maker, product, serial, interfaces) in USB.items():
        base = Path(PCI) / node
        for name, value in (("idVendor", vid), ("idProduct", pid), ("manufacturer", maker), ("product", product),
                            ("bDeviceClass", "00"), ("speed", "12"), ("authorized", "1")):
            write(base / name, value + "\n")
        if serial:
            write(base / "serial", serial + "\n")
        for iface, klass, driver, ieee in interfaces:
            write(base / iface / "bInterfaceClass", klass + "\n")
            Path(f"/sys/bus/usb/drivers/{driver}").mkdir(parents=True, exist_ok=True)
            link(base / iface / "driver", f"/sys/bus/usb/drivers/{driver}")
            if ieee:
                write(base / iface / "ieee1284_id", ieee)
        link(f"/sys/bus/usb/devices/{node}", base)
    write(Path(PCI) / "idVendor", "1d6b\n")  # hub raiz
    link("/sys/bus/usb/devices/usb1", PCI)
    for name, (usb, _props, kind) in TTYS.items():
        folder = Path(f"/sys/class/tty/{name}")
        folder.mkdir(parents=True, exist_ok=True)
        if kind is not None:
            write(folder / "type", kind + "\n")
            Path("/sys/devices/platform/serial8250/tty").mkdir(parents=True, exist_ok=True)
            link(folder / "device", "/sys/devices/platform/serial8250")
        else:
            iface = Path(PCI) / usb / f"{usb}:1.0"
            link(folder / "device", iface)
    card = Path("/sys/class/drm/card0-HDMI-A-1")
    write(card / "status", "connected\n")
    write(card / "edid", edid())
    write(card / "modes", "1920x1080\n1280x720\n")
    write("/sys/class/drm/card0-DP-1/status", "disconnected\n")


def build_proc():
    write(FAKE / "input-devices", INPUT)
    subprocess.run(["mount", "--bind", str(FAKE / "input-devices"), "/proc/bus/input/devices"], check=True)


def build_tools(props_by_node):
    tools = FAKE / "bin"
    write(FAKE / "udev.json", json.dumps(props_by_node))
    write(tools / "udevadm", f"""#!/usr/bin/env python3
import json, os, sys
props = json.load(open("{FAKE}/udev.json"))
name = os.path.realpath(sys.argv[sys.argv.index("--name") + 1]) if "--name" in sys.argv else ""
for node, values in props.items():
    if os.path.realpath(node) == name:
        print("\\n".join(f"{{k}}={{v}}" for k, v in values.items()))
        sys.exit(0)
sys.exit(1)
""", 0o755)
    write(tools / "lpstat", f"""#!/bin/sh
STATE=$(cat {CONTROL}/cups 2>/dev/null || echo idle)
case "$1" in
  -v) echo "device for TM-T20: usb://EPSON/TM-T20?serial=X1"; echo "device for Rede_Caixa2: socket://192.0.2.10:9100" ;;
  -p) if [ -z "$2" ]; then
        if [ "$STATE" = disabled ]; then echo "printer TM-T20 disabled since Thu 05 Nov 2026 -"; else echo "printer TM-T20 is idle.  enabled since Thu 05 Nov 2026"; fi
        echo "printer Rede_Caixa2 is idle.  enabled since Thu 05 Nov 2026"
      elif [ "$2" = TM-T20 ] && [ "$STATE" = disabled ]; then echo "printer TM-T20 disabled since Thu 05 Nov 2026 -"
      elif [ "$2" = TM-T20 ] || [ "$2" = Rede_Caixa2 ]; then echo "printer $2 is idle.  enabled since Thu 05 Nov 2026"
      else echo "lpstat: Invalid destination name in list \\"$2\\"." >&2; exit 1; fi ;;
esac
""", 0o755)
    write(tools / "systemctl", "#!/bin/sh\necho active\n", 0o755)
    write(tools / "fuser", f"#!/bin/sh\n[ -f {CONTROL}/busy ] && grep -qx \"$1\" {CONTROL}/busy && {{ echo \" 999\"; exit 0; }}\nexit 1\n", 0o755)


class Emulator(threading.Thread):
    """One pty endpoint answering a serial protocol."""

    def __init__(self, name, kind):
        super().__init__(daemon=True)
        self.master, self.slave = pty.openpty()
        self.name, self.kind = name, kind
        self.path = os.ttyname(self.slave)

    def control(self, key, default):
        try:
            return (CONTROL / key).read_text().strip() or default
        except OSError:
            return default

    def run(self):
        buffer = b""
        while True:
            try:
                data = os.read(self.master, 64)
            except OSError:
                time.sleep(.05)
                continue
            buffer = (buffer + data)[-16:]
            if self.kind == "scale" and b"\x05" in buffer:
                buffer = b""
                if self.control("scale", "01235") != "off":
                    os.write(self.master, b"\x02" + self.control("scale", "01235").encode()[:5] + b"\x03")
            elif self.kind == "printer":
                while b"\x10\x04" in buffer and len(buffer) >= buffer.index(b"\x10\x04") + 3:
                    index = buffer.index(b"\x10\x04")
                    request, buffer = buffer[index + 2], buffer[index + 3:]
                    mode = self.control("printer", "ok")
                    if mode == "off":
                        continue
                    if request == 1:
                        os.write(self.master, b"\x1e" if mode == "offline" else b"\x16")
                    elif request == 4:
                        os.write(self.master, b"\x72" if mode == "nopaper" else b"\x12")


def main():
    CONTROL.mkdir(parents=True, exist_ok=True)
    os.chmod(CONTROL, 0o777)
    build_sys()
    build_proc()
    emulators = {"ttyS0": Emulator("ttyS0", "scale"), "ttyS1": Emulator("ttyS1", "printer"),
                 "ttyACM0": Emulator("ttyACM0", "silent"), "ttyUSB0": Emulator("ttyUSB0", "silent")}
    props = {}
    for name, emulator in emulators.items():
        link(f"/dev/{name}", emulator.path)
        os.chmod(emulator.path, 0o600 if name == "ttyUSB0" else 0o666)  # PL2303 sem permissão
        props[f"/dev/{name}"] = TTYS[name][1]
        emulator.start()
    link("/dev/ttyS2", "/dev/null")
    link("/dev/serial/by-id/usb-GERTEC_PPC930_PP123-if00", "/dev/ttyACM0")
    link("/dev/serial/by-id/usb-Prolific_USB-Serial_Controller-if00-port0", "/dev/ttyUSB0")
    for event in ("event0", "event1", "event5", "event7"):
        write(f"/dev/input/{event}", "", 0o640)  # leitura direta exige root, como no Ubuntu
    build_tools(props)
    write(CONTROL / "ready", "1")
    unplug_watcher(emulators)


def unplug_watcher(emulators):
    """Hot-plug: names listed in /run/fakepdv/unplugged vanish from /dev and /sys."""
    unplugged = set()
    while True:
        try:
            wanted = set((CONTROL / "unplugged").read_text().split())
        except OSError:
            wanted = set()
        for name in wanted - unplugged:
            Path(f"/dev/{name}").unlink(missing_ok=True)
            usb = TTYS.get(name, (None,))[0]
            if usb:
                Path(f"/sys/bus/usb/devices/{usb}").unlink(missing_ok=True)
        for name in unplugged - wanted:
            link(f"/dev/{name}", emulators[name].path)
            usb = TTYS.get(name, (None,))[0]
            if usb:
                link(f"/sys/bus/usb/devices/{usb}", Path(PCI) / usb)
        unplugged = wanted
        time.sleep(.1)


if __name__ == "__main__":
    if sys.argv[1:] == ["setup"]:
        main()

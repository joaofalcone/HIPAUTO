#!/usr/bin/env python3
"""Gera perifericos-br.json a partir do banco oficial usb.ids (linux-usb.org).

Uso: python3 tools/gerar_base_perifericos.py caminho/usb.ids

Somente fabricantes presentes no usb.ids entram na base. Cada produto recebe a
categoria deduzida do nome oficial; quando o nome não indica, vale a categoria
padrão do fabricante. As correções manuais em OVERRIDES foram validadas em campo.
"""

import json
import re
import sys
from pathlib import Path

# VID: (categoria padrão ou None, adaptador USB-serial?)
VENDORS = {
    # Impressoras térmicas, de cupom e de etiquetas
    "04b8": ("printer", False), "0519": ("printer", False), "1504": ("printer", False),
    "0dd4": ("printer", False), "154f": ("printer", False), "0a5f": ("printer", False),
    "1203": ("printer", False), "1343": ("printer", False), "1d90": ("printer", False),
    "2730": ("printer", False), "0b0b": ("printer", False), "0828": ("printer", False),
    "08a6": ("printer", False),
    # Leitores de código de barras
    "0c2e": ("scanner", False), "0536": ("scanner", False), "05f9": ("scanner", False),
    "080c": ("scanner", False), "05e0": ("scanner", False), "1eab": ("scanner", False),
    "067e": (None, False),
    # Pinpads e terminais de pagamento
    "1753": (None, False), "0b00": ("pinpad", False), "11ca": ("pinpad", False),
    "0f14": ("card_reader", False),
    # Biometria
    "05ba": ("biometric", False), "147e": ("biometric", False), "1491": ("biometric", False),
    "16d1": ("biometric", False), "1162": ("biometric", False), "113f": ("biometric", False),
    "0a86": ("biometric", False),
    # Telas touch, balanças, teclados e fabricantes mistos de automação
    "0eef": ("touchscreen", False), "04e7": ("touchscreen", False), "0eb8": ("scale", False),
    "3219": ("keyboard", False), "053a": ("keyboard", False), "0aa7": (None, False),
    "0d3a": (None, False), "0fa8": (None, False), "03f4": (None, False), "0404": (None, False),
    "2fe7": (None, False), "3036": (None, False),
    # Leitores de cartão (smart card / tarja)
    "072f": ("card_reader", False), "076b": ("card_reader", False), "04e6": ("card_reader", False),
    "08e6": ("card_reader", False), "096e": ("card_reader", False),
    # Adaptadores USB-serial (o periférico real está do outro lado do cabo)
    "0403": (None, True), "067b": (None, True), "1a86": (None, True), "10c4": (None, True),
}
SHORT_NAMES = {
    "04b8": "Epson", "0519": "Star Micronics", "1504": "Bixolon", "0dd4": "Custom", "154f": "SNBC",
    "0a5f": "Zebra", "1203": "TSC", "1343": "Citizen", "1d90": "Citizen", "2730": "Citizen",
    "0b0b": "Datamax-O'Neil", "0828": "Sato", "08a6": "Toshiba TEC", "0c2e": "Honeywell (Metrologic)",
    "0536": "Honeywell (Hand Held)", "05f9": "Datalogic", "080c": "Datalogic", "05e0": "Zebra (Symbol)",
    "1eab": "Newland", "067e": "Intermec", "1753": "Gertec", "0b00": "Ingenico", "11ca": "Verifone",
    "0f14": "Ingenico", "05ba": "DigitalPersona", "147e": "UPEK", "1491": "Futronic", "16d1": "Suprema",
    "1162": "SecuGen", "113f": "Integrated Biometrics", "0a86": "Nitgen", "0eef": "eGalax",
    "04e7": "Elo Touch", "0eb8": "Mettler Toledo", "3219": "SMAK", "053a": "Preh KeyTec",
    "0aa7": "Wincor Nixdorf", "0d3a": "Posiflex", "0fa8": "Logic Controls", "03f4": "Diebold",
    "0404": "NCR", "2fe7": "Elgin", "3036": "Control iD", "072f": "ACS", "076b": "HID OmniKey",
    "04e6": "SCM Microsystems", "08e6": "Gemalto", "096e": "Feitian", "0403": "FTDI",
    "067b": "Prolific", "1a86": "QinHeng (WCH)", "10c4": "Silicon Labs",
}
NAME_RULES = (
    ("sat", r"\bs@t\b|\bsat\b|\bmf-?e\b"),
    ("cash_drawer", r"cash drawer|gaveta"),
    ("customer_display", r"operator display|customer display|pole display|\bvfd\b"),
    ("card_reader", r"smart ?card|magnetic (stripe|swipe)|\bmsr\b|card terminal"),
    ("pinpad", r"pin ?pad"),
    ("scanner", r"barcode|bar code|scanner|imager|gryphon|magellan|voyager"),
    ("printer", r"printer|thermal|\btm-|\btsp|\bsrp-|\bttp-|\bb-sv"),
    ("biometric", r"fingerprint|biomini|biometric|\bidbio\b"),
    ("touchscreen", r"touch ?screen|touchmonitor|touch ?controller"),
    ("keyboard", r"keyboard|keypad|tenkey"),
    ("scale", r"\bscale\b"),
)
# Correções validadas em campo que o usb.ids não traz ou nomeia de forma genérica.
OVERRIDES = {
    "1753:c902": {"category": "pinpad", "model": "PPC930", "name": "Pinpad Gertec PPC930"},
    "1753:c901": {"category": "pinpad", "model": "PPC900", "name": "Pinpad Gertec PPC900"},
    "05f9:4005": {"category": "scanner", "model": "PSC", "name": "Scanner fixo Datalogic PSC"},
    "3036:0001": {"category": "printer", "model": "Print iD", "name": "Impressora Control iD Print iD"},
    "3036:0002": {"category": "biometric", "model": "iDBio", "name": "Leitor biométrico Control iD iDBio"},
    "2fe7:0001": {"category": "sat", "model": "SMART S@T", "name": "SAT fiscal Elgin SMART S@T"},
    "3219:0044": {"category": "keyboard", "model": "SKO-44", "name": "Teclado SMAK SKO-44"},
    "0fe6:811e": {"category": "printer", "model": "térmica USB", "manufacturer": "Genérica",
                  "name": "Impressora térmica USB (controladora 0fe6:811e, ex.: Elgin i9)"},
}
# Marcas e modelos do mercado brasileiro reconhecidos pelo nome que o aparelho informa
# (descritor USB, IEEE 1284, fila CUPS). Marcas presentes em várias categorias
# (Elgin, Gertec, Bematech, Tanca, Sweda, Control iD) só valem junto com o modelo.
BRAND_WORDS = {
    "printer": ["epson", "daruma", "bixolon", "argox", "custom kube", "elgin i9", "elgin i8", "elgin i7",
                "elgin l42", "bematech mp-4200", "bematech mp-2800", "bematech mp-100", "mp-4200",
                "tanca tp-", "sweda si-", "control id print", "print id", "gertec g250", "rongta",
                "xprinter", "hprt", "zebra zd", "zebra gc", "tsc tdp", "tsc ttp", "star tsp"],
    "scale": ["toledo", "filizola", "urano", "ramuza", "welmy", "balmak", "elgin dp", "prix 3", "prix 4",
              "prix 5", "prix fit"],
    "pinpad": ["ppc930", "ppc900", "ppc910", "ipp320", "ipp350", "ingenico", "verifone", "lane 3000",
               "lane 5000", "pax d180", "pax d200"],
    "scanner": ["datalogic", "honeywell", "metrologic", "voyager", "newland", "zebra ds", "symbol ls",
                "elgin flash", "bematech s-", "tanca ts-5", "quickscan", "gryphon", "magellan"],
    "sat": ["d-sat", "dsat", "gersat", "linker", "rb-1000", "rb-2000", "ss-1000", "ss-2000", "ts-1000",
            "tm-1000", "sat id", "easy s@t", "smart s@t", "mfe", "mf-e"],
    "biometric": ["nitgen", "hamster", "ud4500", "idbio", "digitalpersona", "futronic", "suprema",
                  "secugen", "u.are.u"],
    "keyboard": ["sko-44", "sko44", "tec-e 44", "tec-e44", "tec-55", "smartkey"],
    "cash_drawer": ["gaveta", "cash drawer"],
}


def parse_usb_ids(text):
    vendors, current = {}, None
    for line in text.splitlines():
        if line.startswith("C "):
            break
        if not line.strip() or line.startswith("#"):
            continue
        if not line.startswith("\t"):
            current = line[:4].lower()
            vendors[current] = {"name": line[6:].strip(), "products": {}}
        elif not line.startswith("\t\t") and current:
            vendors[current]["products"][line[1:5].lower()] = line[7:].strip()
    return vendors


def product_category(name, default):
    lowered = name.lower()
    for category, pattern in NAME_RULES:
        if re.search(pattern, lowered):
            return category
    return default


def build(usb_ids_text, version):
    ids = parse_usb_ids(usb_ids_text)
    vendors, products = {}, {}
    for vid, (category, adapter) in sorted(VENDORS.items()):
        if vid not in ids:
            raise SystemExit(f"VID {vid} não existe no usb.ids; remova ou corrija")
        vendors[vid] = {"manufacturer": SHORT_NAMES[vid], "official": ids[vid]["name"],
                        "category": category, **({"adapter": True} if adapter else {})}
        for pid, name in sorted(ids[vid]["products"].items()):
            entry = {"model": name}
            if adapter:
                entry["adapter"] = True
            else:
                entry["category"] = product_category(name, category)
            products[f"{vid}:{pid}"] = entry
    for key, value in OVERRIDES.items():
        products[key] = {**products.get(key, {}), **value}
    return {"source": "usb.ids (http://www.linux-usb.org/usb.ids)", "usbIdsVersion": version,
            "vendors": vendors, "products": products, "brandWords": BRAND_WORDS}


def main():
    source = Path(sys.argv[1])
    text = source.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^# Version:\s*(\S+)", text, re.M)
    data = build(text, match.group(1) if match else "desconhecida")
    target = Path(__file__).resolve().parent.parent / "perifericos-br.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['vendors'])} fabricantes, {len(data['products'])} produtos -> {target}")


if __name__ == "__main__":
    main()

"""Classificação de periféricos e catálogo de equipamentos homologados."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any

from .system import resource_path

# Identidades USB exatas de equipamentos conhecidos.
KNOWN_USB = {
    "05f9:4005": ("scanner", "Scanner fixo PSC/Datalogic"),
    "1753:c902": ("pinpad", "Pinpad Gertec PPC930"),
}
# Fabricantes cujo VID identifica com segurança o tipo de equipamento no PDV.
VENDOR_HINTS = {
    "04b8": "printer",   # Seiko Epson
    "0b1b": "printer",   # Bematech
    "0c2e": "scanner",   # Honeywell / Metrologic
    "05f9": "scanner",   # Datalogic
    "05e0": "scanner",   # Symbol / Zebra
    "0b00": "pinpad",    # Ingenico
}
RULES = (
    ("scale", ("scale", "balanca", "toledo", "filizola", "urano", "prix")),
    ("pinpad", ("pinpad", "ingenico", "gertecppc", "ppc930", "verifone")),
    ("biometric", ("biometric", "biometria", "fingerprint", "ud4500", "idbio")),
    ("printer", ("printer", "impressora", "epson", "bematech", "sweda", "elgin", "thermal", "daruma")),
    ("scanner", ("scanner", "barcode", "datalogic", "honeywell", "metrologic", "symbol")),
    ("touchscreen", ("touchscreen", "touchcontroller", "touchpanel", "egalax", "elotouch")),
    ("keyboard", ("keyboard", "teclado")),
)
ORDER = {"pinpad": 0, "scanner": 1, "scale": 2, "printer": 3, "keyboard": 4,
         "biometric": 5, "touchscreen": 6, "monitor": 7}


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def classify(name: str | None) -> str:
    text = norm(name)
    return next((category for category, words in RULES if any(word in text for word in words)), "unknown")


def known_usb(vendor_id: str | None, product_id: str | None) -> tuple[str, str] | None:
    return KNOWN_USB.get(f"{vendor_id}:{product_id}".lower()) if vendor_id and product_id else None


def sort_key(device: dict[str, Any]) -> tuple[int, str, str]:
    return (ORDER.get(device.get("category") or "", 9), norm(device.get("name")), device.get("id") or "")


@lru_cache(maxsize=1)
def catalog() -> tuple[dict[str, Any], ...]:
    try:
        data = json.loads(resource_path("homologados-linux.json").read_text(encoding="utf-8"))
        return tuple(data.get("devices", []))
    except (OSError, ValueError):
        return ()


def homologation(category: str | None, name: str | None, vendor_id: str | None = None,
                 product_id: str | None = None) -> dict[str, Any]:
    if not category or category == "unknown":
        return {"status": "unknown", "label": "Homologação não aplicável"}
    categories = {category, "touchscreen"} if category == "monitor" else {category}
    usb = f"{vendor_id}:{product_id}".lower()
    text = norm(name)
    candidates = sorted((item for item in catalog() if item.get("category") in categories),
                        key=lambda item: len(norm(item.get("model"))), reverse=True)
    for item in candidates:
        ids = [value.lower() for value in item.get("usbIds", [])]
        model, maker = norm(item.get("model")), norm(item.get("manufacturer"))
        if usb in ids or (model and model in text and (not maker or maker in text)):
            return {"status": "homologated", "label": "Homologado Linux",
                    "manufacturer": item.get("manufacturer"), "model": item.get("model"),
                    "notes": item.get("notes")}
    if category == "monitor":
        return {"status": "unknown", "label": "Monitor comum; homologação não exigida"}
    return {"status": "not_homologated", "label": "Não consta na lista Linux homologada"}

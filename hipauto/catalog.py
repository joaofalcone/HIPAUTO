"""Classificação de periféricos e catálogo de equipamentos homologados."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any

from .system import resource_path

# Palavras de tipo (genéricas); a ordem resolve nomes com mais de uma palavra.
RULES = (
    ("cash_drawer", ("cashdrawer", "gaveta")),
    ("customer_display", ("customerdisplay", "operatordisplay", "poledisplay", "displaycliente")),
    ("card_reader", ("smartcard", "magneticstripe", "magneticswipe", "leitordecartao", "ccid")),
    ("scale", ("scale", "balanca")),
    ("pinpad", ("pinpad",)),
    ("biometric", ("biometric", "biometria", "biometrico", "fingerprint")),
    ("printer", ("printer", "impressora", "thermal", "receipt")),
    ("scanner", ("scanner", "barcode", "leitordecodigo", "imager")),
    ("touchscreen", ("touchscreen", "touchcontroller", "touchpanel", "touchmonitor", "egalax", "elotouch")),
    ("keyboard", ("keyboard", "teclado")),
)
SAT_PATTERN = re.compile(r"\bs@t\b|\bsat\b|\bmf-?e\b")
MIN_BRAND_LENGTH = 4  # palavras curtas demais casariam com nomes aleatórios
ORDER = {"pinpad": 0, "scanner": 1, "scale": 2, "printer": 3, "sat": 4, "cash_drawer": 5,
         "keyboard": 6, "biometric": 7, "card_reader": 8, "customer_display": 9, "touchscreen": 10,
         "monitor": 11}


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


@lru_cache(maxsize=1)
def usb_database() -> dict[str, Any]:
    try:
        return json.loads(resource_path("perifericos-br.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"vendors": {}, "products": {}, "brandWords": {}}


@lru_cache(maxsize=1)
def brand_words() -> tuple[tuple[str, str], ...]:
    """(normalized word, category), longest first so specific models win over brands."""
    pairs = {(norm(word), category) for category, words in usb_database().get("brandWords", {}).items()
             for word in words if len(norm(word)) >= MIN_BRAND_LENGTH}
    return tuple(sorted(pairs, key=lambda pair: (-len(pair[0]), pair[0])))


def classify(name: str | None) -> str:
    text = norm(name)
    if not text:
        return "unknown"
    if SAT_PATTERN.search(str(name).lower()):
        return "sat"
    rule = next((category for category, words in RULES if any(word in text for word in words)), None)
    if rule:
        return rule
    return next((category for word, category in brand_words() if word in text), "unknown")


def usb_identity(vendor_id: str | None, product_id: str | None) -> dict[str, Any]:
    """Manufacturer, model, category and adapter flag from the bundled usb.ids subset."""
    if not vendor_id:
        return {}
    database = usb_database()
    vendor = database["vendors"].get(vendor_id.lower(), {})
    product = database["products"].get(f"{vendor_id}:{product_id}".lower(), {}) if product_id else {}
    identity = {"manufacturer": product.get("manufacturer") or vendor.get("manufacturer"),
                "model": product.get("model"), "name": product.get("name"),
                "category": product.get("category") or vendor.get("category"),
                "adapter": bool(product.get("adapter") or vendor.get("adapter"))}
    return {key: value for key, value in identity.items() if value}


def display_name(manufacturer: str | None, model: str | None) -> str:
    manufacturer, model = (manufacturer or "").strip(), (model or "").strip()
    if not model:
        return manufacturer
    if not manufacturer or norm(model).startswith(norm(manufacturer)[:5]):
        return model
    return f"{manufacturer} {model}"


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

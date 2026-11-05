"""Segunda camada de revisão: precisão da identificação no mercado brasileiro."""

import json
import os
import pty
import sys
import threading
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hipauto import catalog, checks, discovery  # noqa: E402

# Nomes como os aparelhos se apresentam (descritor USB, IEEE 1284 ou fila CUPS).
MARKET = {
    "printer": ["Elgin i9 Full", "ELGIN i8", "Bematech MP-4200 TH", "EPSON TM-T20X", "Daruma DR800",
                "Tanca TP-650", "Sweda SI-300S", "Control iD Print iD Touch", "Gertec G250",
                "Bixolon SRP-350III", "Argox OS-214 plus", "Zebra ZD220", "POS-80 Thermal Printer",
                "USB Receipt Printer", "Custom KUBE II"],
    "scale": ["Toledo Prix 3 Fit", "Filizola CS15", "Urano POP-S", "Ramuza DP-15", "Welmy BCW",
              "Balança Elgin DP-15", "Mettler Scale"],
    "sat": ["Tanca SAT TS-1000", "Dimep D-SAT 2.0", "Elgin Linker II", "Bematech RB-2000 FI",
            "Sweda SS-2000", "Gertec GerSAT-W", "Control iD SAT iD", "Kryptus Easy S@T", "SMART S@T",
            "Tanca MFE TM-1000"],
    "pinpad": ["Gertec PPC930", "Gertec PPC910", "Ingenico Lane 3000", "Ingenico iPP320", "Verifone VX 820",
               "PAX D180"],
    "scanner": ["Honeywell Voyager 1250g", "Zebra DS2208", "Datalogic QuickScan QD2430", "Elgin Flash I",
                "Newland HR22 Dorada", "Bematech S-500", "Metrologic MS9540", "USB Barcode Scanner",
                "Datalogic Magellan 1100i"],
    "biometric": ["Nitgen Hamster DX", "Control iD iDBio", "SMAK UD4500", "DigitalPersona U.are.U 4500",
                  "Futronic FS80H", "Fingerprint Reader"],
    "keyboard": ["SMAK SKO-44", "Gertec TEC-E 44", "Keytec Smartkey 44", "USB Keyboard"],
    "cash_drawer": ["Gaveta de dinheiro Bematech", "Posiflex Cash Drawer"],
    "touchscreen": ["eGalax TouchScreen", "Elo TouchSystems 2216 AccuTouch", "ILITEK Touch Controller"],
    "card_reader": ["ACS ACR38 Smart Card Reader", "Magnetic Stripe Reader"],
}
# Aparelhos comuns que NÃO são periféricos de PDV e não podem ganhar categoria.
NOT_POS = ["Kingston DataTraveler 3.0", "SanDisk Cruzer Blade", "Generic Mass Storage", "Logitech USB Receiver",
           "Realtek USB Ethernet", "Intel Bluetooth", "USB2.0 HD UVC WebCam", "Microsoft Satellite Hub",
           "PixArt USB Optical Mouse", "Ubuntu Linux Hub"]


class MarketClassificationTests(unittest.TestCase):
    def test_every_market_device_gets_its_category(self):
        wrong = [(name, expected, catalog.classify(name)) for expected, names in MARKET.items()
                 for name in names if catalog.classify(name) != expected]
        self.assertEqual(wrong, [])

    def test_common_non_pos_devices_stay_unknown(self):
        wrong = [(name, catalog.classify(name)) for name in NOT_POS if catalog.classify(name) != "unknown"]
        self.assertEqual(wrong, [])


class DatabaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.db = json.loads((ROOT / "perifericos-br.json").read_text(encoding="utf-8"))

    def test_ids_are_well_formed(self):
        for vid in self.db["vendors"]:
            self.assertRegex(vid, r"^[0-9a-f]{4}$")
        for key in self.db["products"]:
            self.assertRegex(key, r"^[0-9a-f]{4}:[0-9a-f]{4}$")

    def test_categories_are_known_to_the_interface(self):
        valid = set(catalog.ORDER) | {"unknown"}
        used = {p.get("category") for p in self.db["products"].values() if p.get("category")}
        used |= {v["category"] for v in self.db["vendors"].values() if v.get("category")}
        self.assertLessEqual(used, valid)

    def test_brazilian_manufacturers_present(self):
        makers = {v["manufacturer"] for v in self.db["vendors"].values()}
        self.assertLessEqual({"Elgin", "Gertec", "SMAK", "Control iD", "Epson", "Ingenico", "Datalogic"}, makers)

    def test_official_source_matches_when_available(self):
        source = os.environ.get("USB_IDS")
        if not source:
            self.skipTest("defina USB_IDS=caminho/usb.ids para conferir contra a fonte oficial")
        sys.path.insert(0, str(ROOT / "tools"))
        import gerar_base_perifericos as generator
        official = generator.parse_usb_ids(Path(source).read_text(encoding="utf-8", errors="replace"))
        for vid, vendor in self.db["vendors"].items():
            self.assertEqual(vendor["official"], official[vid]["name"])
        for key, product in self.db["products"].items():
            vid, pid = key.split(":")
            if key not in generator.OVERRIDES:
                self.assertEqual(product["model"], official[vid]["products"][pid])


class SerialPrinterTests(unittest.TestCase):
    def _printer(self, replies):
        master, slave = pty.openpty()

        def serve():
            for reply in replies:
                if os.read(master, 3)[:2] == b"\x10\x04":
                    os.write(master, reply)

        thread = threading.Thread(target=serve)
        thread.start()
        device = discovery.new_device(id="serial:x", category="printer", port=os.ttyname(slave),
                                      printer_protocol="ESC/POS", port_details={"baudrate": 9600})
        try:
            with unittest.mock.patch.object(checks, "port_in_use", return_value=False):
                return checks.test_device(device)
        finally:
            thread.join(2)
            os.close(master)
            os.close(slave)

    def test_online_printer_ok(self):
        self.assertEqual(self._printer([b"\x16", b"\x12"])["status"], "ok")

    def test_paper_end_is_failure(self):
        outcome = self._printer([b"\x16", b"\x72"])
        self.assertEqual(outcome["status"], "error")
        self.assertIn("papel", outcome["detail"])

    def test_offline_is_warning(self):
        self.assertEqual(self._printer([b"\x1e", b"\x12"])["status"], "warning")


class MergePrecisionTests(unittest.TestCase):
    def test_identical_devices_on_different_ports_stay_separate(self):
        a = discovery.new_device(id="usb:1-2", source="usb", usb_node="1-2", vendor_id="0c2e", product_id="0b81")
        b = discovery.new_device(id="usb:1-3", source="usb", usb_node="1-3", vendor_id="0c2e", product_id="0b81")
        self.assertEqual(len(discovery.merge_interfaces([a, b])), 2)


if __name__ == "__main__":
    unittest.main()

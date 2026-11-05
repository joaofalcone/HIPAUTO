import os
import pty
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipauto import catalog, checks, discovery, environment, protocols, smak, system  # noqa: E402


def dev(**fields):
    return discovery.new_device(**fields)


class P05Tests(unittest.TestCase):
    def test_decode_weights(self):
        self.assertEqual(protocols.decode_p05(b"\x0200000\x03")["weight"], "0 kg")
        self.assertEqual(protocols.decode_p05(b"\x0214385\x03")["weight"], "14.385 kg")
        self.assertEqual(protocols.decode_p05(b"\x0201200\x03")["weight"], "1.2 kg")

    def test_decode_states_and_rejects_garbage(self):
        self.assertEqual(protocols.decode_p05(b"\x02IIIII\x03")["state"], "peso instável")
        self.assertIsNone(protocols.decode_p05(b"00000"))
        self.assertIsNone(protocols.decode_p05(b"\x021234\x03"))

    def _exchange(self, reply):
        master, slave = pty.openpty()
        port = os.ttyname(slave)

        def responder():
            if os.read(master, 1) == b"\x05":
                os.write(master, reply)

        thread = threading.Thread(target=responder)
        thread.start()
        try:
            return protocols.probe_p05(port, 1.0)
        finally:
            thread.join(1)
            os.close(master)
            os.close(slave)

    def test_real_serial_exchange(self):
        result = self._exchange(b"\x0200000\x03")
        self.assertTrue(result["matched"])
        self.assertEqual(result["decoded"]["weight"], "0 kg")

    def test_exchange_tolerates_leading_noise(self):
        self.assertTrue(self._exchange(b"\x00\x0201500\x03")["matched"])

    def test_generic_weight_parse(self):
        self.assertEqual(protocols.parse_weight("ST,GS  002,350kg", {"unit": "kg"}), "2.35 kg")
        self.assertIsNone(protocols.parse_weight("abc", {"weight_regex": "("}))


class EscPosTests(unittest.TestCase):
    def test_status_byte_rules(self):
        self.assertTrue(protocols.is_escpos_status(b"\x12"))
        self.assertTrue(protocols.is_escpos_status(b"\x16"))
        self.assertFalse(protocols.is_escpos_status(b"\x05"))
        self.assertFalse(protocols.is_escpos_status(b"\x12\x12"))

    def test_pty_printer_answers_status(self):
        master, slave = pty.openpty()

        def printer():
            if os.read(master, 3) == b"\x10\x04\x01":
                os.write(master, b"\x16")

        thread = threading.Thread(target=printer)
        thread.start()
        try:
            result = protocols.probe_escpos(os.ttyname(slave))
        finally:
            thread.join(1)
            os.close(master)
            os.close(slave)
        self.assertTrue(result["matched"])


class CatalogTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(catalog.classify("Gertec PPC930"), "pinpad")
        self.assertEqual(catalog.classify("Gertec TEC-E 44 keyboard"), "keyboard")
        self.assertEqual(catalog.classify("ELAN Touchpad"), "unknown")
        self.assertEqual(catalog.classify("eGalax TouchScreen"), "touchscreen")
        self.assertEqual(catalog.classify("Tanca TS-1000 SAT"), "sat")
        self.assertEqual(catalog.classify("Toledo Prix 4"), "scale")
        self.assertEqual(catalog.classify("Bematech MP-4200 TH"), "printer")
        self.assertEqual(catalog.classify("Satellite Pro"), "unknown")

    def test_usb_database_is_official_and_rich(self):
        db = catalog.usb_database()
        self.assertTrue(db["usbIdsVersion"])
        self.assertGreater(len(db["products"]), 500)
        self.assertEqual(catalog.usb_identity("2fe7", "0001")["category"], "sat")
        self.assertEqual(catalog.usb_identity("3219", "0044")["manufacturer"], "SMAK")
        self.assertEqual(catalog.usb_identity("0d3a", "0206")["category"], "cash_drawer")
        self.assertTrue(catalog.usb_identity("067b", "2303")["adapter"])
        self.assertEqual(catalog.usb_identity("04b8", "ffff")["category"], "printer")

    def test_display_name_avoids_duplicates(self):
        self.assertEqual(catalog.display_name("Epson", "TM-T20"), "Epson TM-T20")
        self.assertEqual(catalog.display_name("EPSON", "EPSON TM-T20"), "EPSON TM-T20")

    def test_homologation_by_usb_id_and_name(self):
        self.assertEqual(catalog.homologation("pinpad", "x", "1753", "c902")["status"], "homologated")
        self.assertEqual(catalog.homologation("keyboard", "SMAK SMAK SKO-44")["status"], "homologated")
        self.assertEqual(catalog.homologation("printer", "Marca X")["status"], "not_homologated")

    def test_sort_tolerates_missing_names(self):
        items = [dev(id="b", category="printer", name=None), dev(id="a", category="pinpad", name="P")]
        self.assertEqual([d["id"] for d in sorted(items, key=catalog.sort_key)], ["a", "b"])


class DiscoveryTests(unittest.TestCase):
    def test_usb_node_from_sysfs_path(self):
        path = "/sys/devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2.3/1-2.3:1.0/ttyUSB0"
        with patch.object(Path, "resolve", lambda self: Path(str(self))):
            self.assertEqual(discovery.usb_node(path), "1-2.3")

    def test_interfaces_of_one_device_are_merged(self):
        serial = dev(id="serial:ttyACM0", source="serial", category="pinpad", name="PPC930", usb_node="1-4",
                     vendor_id="1753", product_id="c902", port="/dev/ttyACM0")
        hid = dev(id="input:event7", source="input", category="scanner", name="HID", usb_node="1-4",
                  path="/dev/input/event7")
        usb = dev(id="usb:1-4", source="usb", category="pinpad", name="Gertec", usb_node="1-4",
                  vendor_id="1753", product_id="c902", serial_number="ABC")
        other = dev(id="usb:1-5", source="usb", category="scanner", name="Scanner", usb_node="1-5")
        merged = discovery.merge_interfaces([usb, hid, other, serial])
        self.assertEqual({d["id"] for d in merged}, {"serial:ttyACM0", "usb:1-5"})
        kept = next(d for d in merged if d["id"] == "serial:ttyACM0")
        self.assertEqual(kept["serial_number"], "ABC")
        self.assertEqual(len(kept["interfaces"]), 2)

    def test_usb_printer_queue_absorbs_physical_printer(self):
        physical = dev(id="usb:1-1", source="usb", category="printer", name="EPSON TM-T20", product="TM-T20",
                       connection="USB", serial_number="X1", path="/sys/bus/usb/devices/1-1")
        queue = dev(id="printer:TM", source="printer", category="printer", name="TM", connection="USB",
                    queue="TM", printer_uri="usb://EPSON/TM-T20?serial=X1")
        result = discovery.attach_usb_printers([physical, queue])
        self.assertEqual([d["id"] for d in result], ["printer:TM"])
        self.assertEqual(result[0]["usb_path"], "/sys/bus/usb/devices/1-1")

    def test_usb_queue_without_printer_is_reported(self):
        queue = dev(id="printer:TM", source="printer", category="printer", name="TM", connection="USB",
                    queue="TM", printer_uri="usb://EPSON/TM-T20")
        self.assertEqual(discovery.attach_usb_printers([queue])[0]["status"], "error")

    def test_offline_network_printer_is_kept_as_failure(self):
        def fake_run(cmd, timeout=5.0):
            if cmd == ["lpstat", "-p"]:
                return 0, "printer rede is idle.  enabled since x"
            return 0, "device for rede: socket://10.255.255.1:9100"
        with patch.object(discovery, "run", fake_run), patch.object(discovery, "network_reachable", return_value=False):
            queues = discovery.cups_queues()
        self.assertEqual(len(queues), 1)
        self.assertEqual(queues[0]["status"], "error")

    def test_ieee1284_parse(self):
        info = discovery.parse_ieee1284("MFG:EPSON;CMD:ESC/POS;MDL:TM-T20;CLS:PRINTER;")
        self.assertEqual((info["manufacturer"], info["model"], info["commands"]), ("EPSON", "TM-T20", "ESC/POS"))

    def test_adapter_port_is_not_named_after_chip_maker(self):
        props = {"ID_VENDOR_ID": "067b", "ID_MODEL_ID": "2303", "ID_VENDOR": "Prolific"}
        with patch.object(discovery.Path, "iterdir", return_value=[Path("/dev/ttyUSB0")]), \
                patch.object(discovery, "udev_properties", return_value=props), \
                patch.object(discovery, "usb_node", return_value="1-3"):
            device = discovery.serial_devices({"aliases": {}})[0]
        self.assertEqual(device["category"], "unknown")
        self.assertIsNone(device["manufacturer"])
        self.assertIn("PL2303", device["adapter"])

    def test_serial_escpos_printer_identified(self):
        device = dev(id="serial:ttyS1", category="unknown", name="Porta", port="/dev/ttyS1")
        with patch.object(discovery, "port_in_use", return_value=False), \
                patch.object(discovery.protocols, "probe_p05", return_value={"matched": False}), \
                patch.object(discovery.protocols, "probe_escpos",
                             return_value={"matched": True, "baudrate": 115200, "hex": "12"}):
            discovery.identify_serial([device])
        self.assertEqual((device["category"], device["port_details"]["baudrate"]), ("printer", 115200))

    def test_broken_source_does_not_stop_discovery(self):
        with patch.object(discovery, "input_devices", side_effect=RuntimeError("falhou")), \
                patch.object(discovery, "run", return_value=(1, "")), \
                patch.object(discovery.smak, "probe", return_value={}):
            discovery.discover()
        self.assertTrue(any("falhou" in item for item in discovery.LAST_ERRORS))

    def test_edid_identifies_monitor(self):
        edid = bytearray(128)
        edid[0:8] = b"\x00\xff\xff\xff\xff\xff\xff\x00"
        code = ((ord("S") - 64) << 10) | ((ord("A") - 64) << 5) | (ord("M") - 64)
        edid[8], edid[9] = code >> 8, code & 0xFF
        edid[54:59] = b"\x00\x00\x00\xfc\x00"
        edid[59:72] = b"S24F350\n     "
        edid[21], edid[22] = 53, 30
        info = discovery.parse_edid(bytes(edid))
        self.assertEqual((info["manufacturer"], info["model"]), ("Samsung", "S24F350"))
        self.assertEqual(info["diagonal"], 24.0)

    def test_scale_identification_promotes_only_valid_reply(self):
        device = dev(id="serial:ttyS4", category="unknown", name="Porta", port="/dev/ttyS4")
        probe = {"matched": True, "hex": "02 30 30 30 30 30 03",
                 "decoded": {"kind": "weight", "payload": "00000", "weight": "0 kg"}}
        with patch.object(discovery, "port_in_use", return_value=False), \
                patch.object(discovery.protocols, "probe_p05", return_value=probe):
            discovery.identify_serial([device])
        self.assertEqual((device["category"], device["scale_protocol"]), ("scale", "P05"))

    def test_busy_port_is_not_probed(self):
        device = dev(id="serial:ttyS4", category="unknown", name="Porta", port="/dev/ttyS4")
        with patch.object(discovery, "port_in_use", return_value=True), \
                patch.object(discovery.protocols, "probe_p05") as probe:
            discovery.identify_serial([device])
        probe.assert_not_called()

    def test_smak_renames_ps2_keyboard(self):
        keyboard = dev(id="input:event0", category="keyboard", name="AT Translated", connection="PS/2")
        with patch.object(discovery.smak, "probe", return_value={"detected": True, "firmware": "1.0"}):
            discovery.identify_smak([keyboard])
        self.assertEqual(keyboard["name"], "SMAK SKO-44")

    def test_discover_never_configures_cups(self):
        calls = []
        def fake_run(cmd, timeout=5.0):
            calls.append(cmd[0])
            return 1, ""
        with patch.object(discovery, "run", fake_run), patch.object(discovery.smak, "probe", return_value={}):
            discovery.discover()
        self.assertNotIn("lpadmin", calls)
        self.assertNotIn("lpoptions", calls)


class SerialIdentificationTests(unittest.TestCase):
    def sysfs(self, target_parts, files):
        import tempfile
        root = Path(tempfile.mkdtemp())
        target = root.joinpath(*target_parts)
        target.mkdir(parents=True)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        link = root / "class/tty/ttyS4/device"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        return str(root)

    def test_intel_amt_serial_over_lan(self):
        root = self.sysfs(["devices/pci0000:00/0000:00:16.3"],
                          {"devices/pci0000:00/0000:00:16.3/vendor": "0x8086\n",
                           "devices/pci0000:00/0000:00:16.3/class": "0x070002\n"})
        hardware = discovery.serial_hardware("ttyS4", root)
        self.assertEqual(hardware["kind"], "amt")
        self.assertIn("Intel AMT", discovery.serial_port_name("ttyS4", hardware))

    def test_pci_serial_card_brand(self):
        root = self.sysfs(["devices/pci0000:00/0000:03:00.0"],
                          {"devices/pci0000:00/0000:03:00.0/vendor": "0x1c00\n",
                           "devices/pci0000:00/0000:03:00.0/class": "0x070002\n"})
        hardware = discovery.serial_hardware("ttyS4", root)
        self.assertEqual(discovery.serial_port_name("ttyS4", hardware), "Porta serial ttyS4 (placa WCH)")

    def test_motherboard_com_port(self):
        root = self.sysfs(["devices/pnp0/00:05"], {})
        hardware = discovery.serial_hardware("ttyS4", root)
        self.assertEqual(discovery.serial_port_name("ttyS0", hardware), "Porta COM1 (placa-mãe)")

    def test_unidentified_port_is_explained(self):
        cases = [("permission", None, b"", "warning", "dialout"),
                 ("silent", {"CTS": True, "DSR": True, "DCD": False, "RI": False}, b"", "detected", "CTS, DSR"),
                 ("silent", {"CTS": False, "DSR": False, "DCD": False, "RI": False}, b"", "idle", "livre"),
                 ("silent", None, b"", "idle", "protocolos testados"),
                 ("silent", None, b"xyz", "detected", "dados")]
        for reason, lines, data, status, text in cases:
            with self.subTest(reason=reason, lines=lines):
                device = dev(id="serial:ttyS0", category="unknown", port="/dev/ttyS0")
                discovery.finish_unidentified(device, reason, lines, data)
                self.assertEqual(device["category"], "serial_port")
                self.assertEqual(device["status"], status)
                self.assertIn(text, device["detail"])

    def test_streaming_scale_detected_passively(self):
        master, slave = pty.openpty()

        def stream():  # a balança transmite sozinha, sem receber comandos
            for _ in range(4):
                time.sleep(.1)
                os.write(master, b"ST,GS,   1.250kg\r\n")

        thread = threading.Thread(target=stream)
        thread.start()
        try:
            heard = protocols.listen(os.ttyname(slave), timeout=.6)
        finally:
            thread.join()
            os.close(master)
            os.close(slave)
        self.assertEqual(heard["weight"], "1.25 kg")

    def test_cups_queue_name_is_readable(self):
        def fake_run(cmd, timeout=5.0):
            return 0, ("printer EPSON_L1250_Series is idle.  enabled" if cmd == ["lpstat", "-p"]
                       else "device for EPSON_L1250_Series: usb://EPSON/L1250")
        with patch.object(discovery, "run", fake_run):
            self.assertEqual(discovery.cups_queues()[0]["name"], "EPSON L1250 Series")


class SmakCommandTests(unittest.TestCase):
    def test_source_command_targets_entry_script(self):
        command = smak.command()
        self.assertEqual(command[-1], "--smak-probe")
        self.assertTrue(command[1].endswith("hipauto_desktop.py"))

    def test_frozen_command_reuses_executable(self):
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(smak.command(), [sys.executable, "--smak-probe"])

    def test_entry_handles_probe_without_gui(self):
        import hipauto_desktop
        with patch.object(smak, "worker") as worker:
            self.assertEqual(hipauto_desktop.main(["--smak-probe"]), 0)
        worker.assert_called_once()


class SystemTests(unittest.TestCase):
    def test_frozen_env_restores_library_path(self):
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": "/opt/lib"}), \
                patch.object(sys, "frozen", True, create=True):
            env = system.system_env()
        self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/lib")

    def test_invalid_user_config_is_ignored(self):
        with patch.object(system, "USER_CONFIG", Path("/nonexistent/config.json")):
            self.assertEqual(system.load_config()["serial"]["baudrate"], 9600)


class CheckTests(unittest.TestCase):
    def test_pty_serial_link_ok(self):
        master, slave = pty.openpty()
        try:
            with patch.object(checks, "port_in_use", return_value=False):
                outcome = checks.test_device(dev(id="s", category="pinpad", port=os.ttyname(slave)))
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(outcome["status"], "ok")
        self.assertIn("tested_at", outcome)

    def test_missing_port_fails(self):
        outcome = checks.test_device(dev(id="s", category="pinpad", port="/dev/ttyUSB99"))
        self.assertEqual(outcome["status"], "error")

    def test_unexpected_error_becomes_failure(self):
        with patch.object(checks, "run_test", side_effect=RuntimeError("x")):
            self.assertEqual(checks.test_device(dev(id="s"))["status"], "error")


class EnvironmentTests(unittest.TestCase):
    def test_dialout_warning_only_with_serial_ports(self):
        env = {"groups": ["user"], "configured_groups": [], "cups": "active", "tools": {}, "root": False}
        self.assertTrue(environment.recommendations([dev(id="s", port="/dev/ttyS0")], env))
        self.assertFalse(environment.recommendations([dev(id="k", path="/dev/input/event1")], env))

    def test_snapshot_has_expected_keys(self):
        snap = environment.snapshot()
        self.assertIn("groups", snap)
        self.assertIn("tools", snap)


if __name__ == "__main__":
    unittest.main()

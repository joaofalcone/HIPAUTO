import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipauto import __version__, ui  # noqa: E402

DEVICES = [
    {"id": "scale:1", "category": "scale", "name": "Balança P05", "connection": "Serial RS-232",
     "port": "/dev/ttyS0", "status": "detected", "detail": "Aguardando teste", "driver": "serial",
     "evidence": ["Porta /dev/ttyS0"], "homologation": {"label": "Protocolo P05"},
     "confidence": {"label": "Alta", "reason": "P05"}},
    {"id": "printer:TM", "category": "printer", "name": "EPSON TM-T20", "connection": "USB",
     "queue": "TM", "status": "detected", "detail": "Fila CUPS"},
]
ENV = {"groups": ["user"], "configured_groups": [], "cups": "active", "tools": {}, "root": False}


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(ui.discovery, "discover", side_effect=lambda: [dict(d) for d in DEVICES]),
                        patch.object(ui.environment, "snapshot", return_value=ENV),
                        patch.object(ui.messagebox, "showinfo"), patch.object(ui.messagebox, "showerror")]
        for item in self.patches:
            item.start()
        self.app = ui.HipautoDesktop()
        self.wait_until(lambda: len(self.app.devices) == 2 and not self.app.busy)

    def tearDown(self):
        self.app.close()
        for item in reversed(self.patches):
            item.stop()

    def wait_until(self, condition, timeout=5):
        end = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > end:
                self.fail("A interface não respondeu no prazo")
            self.app.update()
            time.sleep(0.01)

    def all_texts(self, widget):
        texts = []
        for child in widget.winfo_children():
            try:
                texts.append(str(child.cget("text")))
            except tk.TclError:
                pass
            texts.extend(self.all_texts(child))
        return texts

    def test_cards_table_and_notice(self):
        self.assertEqual(set(self.app.cards), {"scale:1", "printer:TM"})
        self.assertTrue(self.app.cards["scale:1"].active)
        self.assertEqual(self.app.tree.item("scale:1", "values")[1], "/dev/ttyS0")
        self.assertEqual(self.app.tree.item("printer:TM", "values")[1], "TM")
        self.assertIn("dialout", self.app.notice_var.get())

    def test_version_only_in_footer(self):
        matches = [text for text in self.all_texts(self.app) if __version__ in text]
        self.assertEqual(matches, [f"v{__version__}"])
        self.assertEqual(self.app.version_label.pack_info()["side"], "left")
        self.assertNotIn(__version__, self.app.title())

    def test_test_all_updates_every_device(self):
        results = {"scale:1": {"status": "ok", "detail": "Peso", "weight": "1.2 kg"},
                   "printer:TM": {"status": "error", "detail": "NÃO OK"}}
        with patch.object(ui.checks, "test_device", side_effect=lambda d: results[d["id"]]):
            self.app.test_all()
            self.assertEqual(self.app.results["scale:1"]["status"], "testing")
            self.wait_until(lambda: not self.app.busy)
        self.assertEqual(self.app.results["printer:TM"]["status"], "error")
        self.assertIn("1 com falha", self.app.status_var.get())
        self.assertIn("1.2 kg", self.app.tree.item("scale:1", "values")[2])

    def test_results_survive_refresh(self):
        with patch.object(ui.checks, "test_device", return_value={"status": "ok", "detail": "OK"}):
            self.app.test_one("scale:1")
            self.wait_until(lambda: not self.app.busy)
        self.app.refresh_devices()
        self.wait_until(lambda: not self.app.busy)
        self.assertEqual(self.app.results["scale:1"]["status"], "ok")

    def test_detail_window_two_columns_and_live_update(self):
        self.app.open_details("scale:1")
        self.app.update()
        labels = [w for w in self.app.details.body.inner.winfo_children() if isinstance(w, tk.Label)]
        self.assertGreaterEqual(len(labels), 16)
        self.assertEqual({int(w.grid_info()["column"]) for w in labels}, {0, 1})
        with patch.object(ui.checks, "test_device", return_value={"status": "ok", "detail": "Peso", "weight": "2 kg"}):
            self.app.details.test_button.invoke()
            self.wait_until(lambda: not self.app.busy)
        values = [w.cget("text") for w in self.app.details.body.inner.winfo_children()]
        self.assertIn("2 kg", values)

    def test_busy_blocks_second_job(self):
        self.app.busy = True
        self.assertFalse(self.app.run_job("x", lambda: None, lambda *_: None))
        self.app.busy = False

    def test_empty_inventory_message(self):
        with patch.object(ui.discovery, "discover", return_value=[]):
            self.app.refresh_devices()
            self.wait_until(lambda: not self.app.busy)
        self.assertFalse(self.app.cards)
        self.assertIn("Nenhum periférico", self.app.empty_label.cget("text"))


class InteractionTests(DesktopTests):
    def test_kpi_filter_and_escape(self):
        results = {"scale:1": {"status": "ok", "detail": "Peso"},
                   "printer:TM": {"status": "error", "detail": "NÃO OK"}}
        with patch.object(ui.checks, "test_device", side_effect=lambda d: results[d["id"]]):
            self.app.test_all()
            self.wait_until(lambda: not self.app.busy)
        self.assertEqual(self.app.tiles["error"].value, 1)
        self.app.set_filter("error")
        self.app.update()
        self.assertEqual(self.app.tree.get_children(), ("printer:TM",))
        self.assertFalse(self.app.cards["scale:1"].canvas.winfo_ismapped())
        self.app.set_filter("error")
        self.assertEqual(len(self.app.tree.get_children()), 2)

    def test_copy_details_and_toast(self):
        self.app.open_details("scale:1")
        self.app.update()
        self.app.details.copy()
        self.assertIn("Balança P05", self.app.clipboard_get())
        self.assertTrue(self.app.place_slaves())

    def test_buttons_disable_while_busy(self):
        self.app._set_busy(True)
        self.assertTrue(self.app.test_all_button.instate(["disabled"]))
        self.app._set_busy(False)
        self.assertTrue(self.app.test_all_button.instate(["!disabled"]))


class DetailRowsTests(unittest.TestCase):
    def test_rows_skip_empty_values(self):
        rows = dict(ui.detail_rows(DEVICES[0], {"status": "ok", "detail": "x", "hex": "02 03"}))
        titles = [title for title, _rows in ui.detail_sections(DEVICES[0], None)]
        self.assertEqual(titles[0], "Identificação")
        self.assertEqual(rows["Estado"], "OK")
        self.assertEqual(rows["Resposta (hex)"], "02 03")
        self.assertNotIn("Firmware", rows)


if __name__ == "__main__":
    unittest.main()

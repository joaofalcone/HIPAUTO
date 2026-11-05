"""Testes de ponta a ponta contra o PDV simulado (tests/e2e/fakepdv.py).

Nada do HIPAUTO é simulado aqui: descoberta, sondas, testes de comunicação e
interface rodam de verdade, como usuário comum (sem root e fora do grupo dialout).
Execute com tests/e2e/run.sh.
"""

import json
import os
import subprocess
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hipauto import checks, discovery, environment, ui  # noqa: E402

CONTROL = Path("/run/fakepdv")
SHOTS = Path(os.environ.get("HIPAUTO_SHOTS", "/tmp"))


def control(name: str, value: str) -> None:
    (CONTROL / name).write_text(value)
    time.sleep(.3)  # o simulador relê os controles a cada 0,1 s


def by_port(devices, port):
    return next(d for d in devices if d.get("port") == port)


class Engine(unittest.TestCase):
    """Descoberta e testes de comunicação reais contra o hardware simulado."""

    @classmethod
    def setUpClass(cls):
        for name in ("scale", "printer", "cups", "busy", "unplugged"):
            (CONTROL / name).unlink(missing_ok=True)
        started = time.monotonic()
        cls.devices = discovery.discover()
        cls.elapsed = time.monotonic() - started
        cls.ids = {d["id"]: d for d in cls.devices}

    def tearDown(self):
        for name in ("scale", "printer", "cups", "busy", "unplugged"):
            (CONTROL / name).unlink(missing_ok=True)

    def test_inventory_matches_the_simulated_pdv(self):
        summary = sorted((d["category"], d["name"]) for d in self.devices)
        expected = {
            ("pinpad", "Pinpad Gertec PPC930"), ("scanner", "Honeywell Imaging & Mobility 1400g"),
            ("scale", "Balança serial - protocolo P05"), ("printer", "Impressora serial ESC/POS"),
            ("printer", "EPSON TM-T20 (fila TM-T20)"), ("printer", "Rede_Caixa2"),
            ("sat", "SAT fiscal Elgin SMART S@T"), ("cash_drawer", "Posiflex Cash Drawer"),
            ("keyboard", "AT Translated Set 2 keyboard"), ("monitor", "Samsung S24F350"),
            ("unknown", "Porta USB-serial (Prolific PL2303)"),
        }
        self.assertEqual(set(summary), expected, summary)
        self.assertEqual(len(self.devices), len(expected), "cada aparelho deve aparecer uma única vez")

    def test_noise_is_ignored(self):
        names = " ".join(d["name"] for d in self.devices)
        self.assertNotIn("Kingston", names)
        self.assertNotIn("Mouse", names)
        self.assertNotIn("Power Button", names)
        self.assertFalse(any(d.get("port") == "/dev/ttyS2" for d in self.devices))

    def test_usb_interfaces_are_unified(self):
        pinpad = by_port(self.devices, "/dev/ttyACM0")
        self.assertEqual(pinpad["serial_number"], "PP123")
        self.assertEqual(pinpad["homologation"]["status"], "homologated")
        self.assertEqual(pinpad["recommended_port"], "/dev/serial/by-id/usb-GERTEC_PPC930_PP123-if00")
        self.assertNotIn("usb:1-4", self.ids)
        self.assertNotIn("usb:1-2", self.ids)  # leitor: HID + USB = um card

    def test_serial_protocol_identification(self):
        scale = by_port(self.devices, "/dev/ttyS0")
        self.assertEqual((scale["scale_protocol"], scale["weight"]), ("P05", "1.235 kg"))
        printer = by_port(self.devices, "/dev/ttyS1")
        self.assertEqual((printer["printer_protocol"], printer["port_details"]["baudrate"]), ("ESC/POS", 9600))

    def test_adapter_without_permission_is_explained(self):
        adapter = by_port(self.devices, "/dev/ttyUSB0")
        self.assertIsNone(adapter["manufacturer"])
        self.assertTrue(any("dialout" in item for item in adapter["evidence"]))

    def test_usb_printer_and_cups(self):
        epson = self.ids["printer:TM-T20"]
        self.assertEqual((epson["manufacturer"], epson["model"], epson["commands"]), ("EPSON", "TM-T20", "ESC/POS"))
        self.assertTrue(any("IEEE 1284" in item for item in epson["evidence"]))
        self.assertEqual(epson["serial_number"], "X1")
        self.assertEqual(self.ids["printer:Rede_Caixa2"]["status"], "error")

    def test_monitor_from_edid(self):
        monitor = self.ids["monitor:HDMI-A-1"]
        self.assertEqual((monitor["resolution"], monitor["diagonal"]), ("1920x1080", 24.0))
        self.assertNotIn("monitor:DP-1", self.ids)

    def test_environment_notices(self):
        env = environment.snapshot()
        texts = " ".join(item["text"] for item in environment.recommendations(self.devices, env))
        self.assertIn("dialout", texts)
        self.assertEqual(env["discovery_errors"], [])

    def test_discovery_is_fast(self):
        self.assertLess(self.elapsed, 15, f"varredura levou {self.elapsed:.1f} s")

    # --------------------------------------------------- testes de comunicação
    def check(self, device_id_or_port):
        device = self.ids.get(device_id_or_port) or by_port(self.devices, device_id_or_port)
        return checks.test_device(device)

    def test_every_device_passes_on_a_healthy_pdv(self):
        expected = {"/dev/ttyACM0": "ok", "/dev/ttyS0": "ok", "/dev/ttyS1": "ok", "/dev/ttyUSB0": "error",
                    "printer:TM-T20": "ok", "printer:Rede_Caixa2": "error", "monitor:HDMI-A-1": "ok"}
        for key, status in expected.items():
            with self.subTest(key):
                self.assertEqual(self.check(key)["status"], status)
        for device in self.devices:
            if device["category"] in {"sat", "cash_drawer", "keyboard", "scanner"}:
                with self.subTest(device["name"]):
                    self.assertEqual(checks.test_device(device)["status"], "ok")

    def test_scale_states(self):
        self.assertEqual(self.check("/dev/ttyS0")["weight"], "1.235 kg")
        control("scale", "IIIII")
        self.assertEqual(self.check("/dev/ttyS0")["status"], "warning")
        control("scale", "off")
        self.assertEqual(self.check("/dev/ttyS0")["status"], "error")

    def test_printer_states(self):
        control("printer", "nopaper")
        self.assertIn("sem papel", self.check("/dev/ttyS1")["detail"])
        control("printer", "offline")
        self.assertEqual(self.check("/dev/ttyS1")["status"], "warning")
        control("printer", "off")
        self.assertEqual(self.check("/dev/ttyS1")["status"], "error")

    def test_cups_queue_disabled(self):
        control("cups", "disabled")
        self.assertEqual(self.check("printer:TM-T20")["status"], "warning")

    def test_port_in_use_by_another_program(self):
        control("busy", "/dev/ttyACM0\n")
        self.assertIn("em uso", self.check("/dev/ttyACM0")["detail"])

    def test_unplugged_device_fails(self):
        pinpad = by_port(self.devices, "/dev/ttyACM0")
        control("unplugged", "ttyACM0")
        self.assertEqual(checks.test_device(pinpad)["status"], "error")
        self.assertFalse(any(d.get("port") == "/dev/ttyACM0" for d in discovery.discover()))


class Interface(unittest.TestCase):
    """Cada opção da interface acionada por eventos reais de mouse e teclado."""

    @classmethod
    def setUpClass(cls):
        for name in ("scale", "printer", "cups", "busy", "unplugged"):
            (CONTROL / name).unlink(missing_ok=True)
        cls.app = ui.HipautoDesktop()
        cls.app.geometry("1366x768+0+0")
        cls.wait(lambda: cls.app._loaded and not cls.app.busy, 30)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.close()
        except tk.TclError:
            pass  # já fechada pelo teste de fechamento

    @classmethod
    def wait(cls, condition, timeout=20):
        end = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > end:
                raise AssertionError("a interface não respondeu no prazo")
            cls.app.update()
            time.sleep(.02)

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()
            time.sleep(.02)

    def click(self, widget, x=None, y=None):
        self.app.update()
        x = widget.winfo_width() // 2 if x is None else x
        y = widget.winfo_height() // 2 if y is None else y
        for sequence in ("<Enter>", "<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>", "<Leave>"):
            if not widget.winfo_exists():  # o clique pode fechar a própria janela
                break
            widget.event_generate(sequence, x=x, y=y)
        self.app.update()

    def key(self, widget, sequence):
        widget.focus_force()
        self.app.update()
        widget.event_generate(sequence)
        self.app.update()

    def shot(self, name):
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(SHOTS / f"e2e-{name}.png")
        except Exception:
            pass

    def visible_ids(self):
        return [d["id"] for d in self.app.visible_devices()]

    def test_01_startup_lists_everything(self):
        self.assertEqual(len(self.app.cards), 11)
        self.assertEqual(self.app.tiles["all"].value, 11)
        self.assertIn("dialout", self.app.notice_var.get())
        self.assertIn("varredura", self.app.status_var.get())
        self.shot("01-inicio")

    def test_02_test_all_button(self):
        self.click(self.app.test_all_button)
        self.assertTrue(self.app.busy)
        self.assertFalse(self.app.refresh_button.instate(["!disabled"]))
        self.wait(lambda: not self.app.busy, 60)
        statuses = {k: v["status"] for k, v in self.app.results.items()}
        self.assertEqual(len(statuses), 11)
        self.assertEqual(statuses["printer:Rede_Caixa2"], "error")
        self.assertEqual(statuses["serial:ttyUSB0"], "error")
        self.assertEqual(statuses["serial:ttyS0"], "ok")
        self.assertIn("2 com falha", self.app.status_var.get())
        self.assertTrue(self.app.place_slaves(), "notificação de conclusão")
        self.shot("02-testar-todos")

    def test_03_kpi_filters(self):
        expected = {"active": 9, "warning": 0, "error": 2}
        for key, count in expected.items():
            with self.subTest(key):
                self.click(self.app.tiles[key])
                self.assertEqual(self.app.filter, key)
                self.assertEqual(len(self.visible_ids()), count)
                self.assertEqual(len(self.app.tree.get_children()), count)
        self.shot("03-filtro-falhas")
        self.click(self.app.tiles["error"])  # clicar de novo limpa
        self.assertEqual(self.app.filter, "all")
        self.click(self.app.tiles["warning"])
        self.assertIn("Nenhum periférico neste filtro", self.app.empty_label.cget("text"))
        self.key(self.app, "<Escape>")
        self.assertEqual(len(self.visible_ids()), 11)

    def test_04_view_switch_and_list(self):
        switch = self.app.view_switch
        self.click(switch, x=switch.widths[0] + switch.widths[1] // 2)
        self.assertEqual(self.app.view, "list")
        self.assertTrue(self.app.list_view.winfo_ismapped())
        self.assertEqual(len(self.app.tree.get_children()), 11)
        self.shot("04-lista")
        self.key(self.app, "<Control-Key-1>")
        self.assertEqual(self.app.view, "cards")
        self.key(self.app, "<Control-Key-2>")
        self.assertEqual(self.app.view, "list")
        self.key(switch, "<Left>")
        self.assertEqual(self.app.view, "cards")

    def test_05_list_opens_details(self):
        self.app.set_view("list")
        self.app.tree.selection_set("serial:ttyS0")
        self.key(self.app.tree, "<Return>")
        self.wait(lambda: self.app.details is not None and self.app.details.winfo_exists())
        self.assertEqual(self.app.details.device_id, "serial:ttyS0")
        self.app.details.destroy()
        self.app.set_view("cards")

    def test_06_card_click_and_detail_actions(self):
        card = self.app.cards["serial:ttyS0"]
        self.click(card.canvas)
        self.wait(lambda: self.app.details is not None and self.app.details.winfo_exists())
        details = self.app.details
        self.pump(.4)
        self.shot("06-detalhes")
        texts = [w.cget("text") for w in details.body.inner.winfo_children()]
        self.assertIn("1.235 kg", texts)
        control("scale", "00500")
        self.click(details.test_button)
        self.wait(lambda: not self.app.busy)
        self.pump(.2)
        self.assertIn("0.5 kg", [w.cget("text") for w in details.body.inner.winfo_children()])
        copy_button = next(w for w in details.winfo_children()[1].winfo_children()
                           if isinstance(w, ui.FlatButton) and w.text == "Copiar dados")
        self.click(copy_button)
        self.assertIn("Balança serial - protocolo P05", self.app.clipboard_get())
        self.assertIn("[Resultado do teste]", self.app.clipboard_get())
        self.key(details, "<Escape>")
        self.assertFalse(details.winfo_exists())

    def test_07_close_button_in_details(self):
        self.app.open_details("monitor:HDMI-A-1")
        details = self.app.details
        close = next(w for w in details.winfo_children()[1].winfo_children()
                     if isinstance(w, ui.FlatButton) and w.text == "Fechar")
        self.click(close)
        self.assertFalse(details.winfo_exists())

    def test_08_keyboard_navigation(self):
        order = self.visible_ids()
        first = self.app.cards[order[0]].canvas
        first.focus_force()
        self.app.update()
        self.key(first, "<Right>")
        self.assertIs(self.app.focus_get(), self.app.cards[order[1]].canvas)
        self.key(self.app.focus_get(), "<Down>")
        self.assertIs(self.app.focus_get(), self.app.cards[order[1 + self.app._columns]].canvas)
        self.key(self.app.focus_get(), "<Return>")
        self.wait(lambda: self.app.details is not None and self.app.details.winfo_exists())
        self.assertEqual(self.app.details.device_id, order[1 + self.app._columns])
        self.app.details.destroy()

    def test_09_shortcuts_f5_and_ctrl_t(self):
        before = dict(self.app.results)
        self.key(self.app, "<F5>")
        self.assertTrue(self.app.busy)
        self.wait(lambda: not self.app.busy, 30)
        self.assertEqual(set(self.app.results), set(before), "resultados preservados após atualizar")
        self.key(self.app, "<Control-t>")
        self.assertTrue(self.app.busy)
        self.wait(lambda: not self.app.busy, 60)

    def test_10_refresh_button_and_hot_unplug(self):
        self.app.open_details("serial:ttyACM0")
        control("unplugged", "ttyACM0")
        self.click(self.app.refresh_button)
        self.wait(lambda: not self.app.busy, 30)
        self.assertNotIn("serial:ttyACM0", self.app.cards)
        self.assertFalse(self.app.details.winfo_exists(), "detalhes de aparelho removido fecham sozinhos")
        self.assertEqual(self.app.tiles["all"].value, 10)
        control("unplugged", "")
        self.click(self.app.refresh_button)
        self.wait(lambda: not self.app.busy, 30)
        self.assertIn("serial:ttyACM0", self.app.cards)

    def test_11_busy_blocks_double_start(self):
        self.click(self.app.test_all_button)
        self.click(self.app.refresh_button)  # ignorado: já há uma tarefa
        self.wait(lambda: not self.app.busy, 60)
        self.assertFalse(self.app.busy)

    def test_12_tooltips(self):
        card = self.app.cards["serial:ttyS0"].canvas
        card.event_generate("<Enter>", x=20, y=20)
        self.pump(1.0)
        self.assertIsNotNone(self.app.tooltip.window)
        self.shot("12-dica")
        card.event_generate("<Leave>")
        self.app.update()
        self.assertIsNone(self.app.tooltip.window)
        for widget in (self.app.refresh_button, self.app.test_all_button, self.app.view_switch, self.app.tiles["all"]):
            widget.event_generate("<Enter>", x=5, y=5)
            self.pump(.9)
            self.assertIsNotNone(self.app.tooltip.window)
            widget.event_generate("<Leave>")
            self.app.update()

    def test_13_toast_click(self):
        self.app.toast("teste")
        self.pump(.3)
        self.click(self.app.place_slaves()[0])
        self.assertFalse(self.app.place_slaves())

    def test_14_compact_mode_and_resize(self):
        self.app.geometry("800x600")
        self.pump(.8)
        self.assertTrue(self.app.compact)
        self.assertFalse(self.app.footer_hint.winfo_ismapped())
        self.assertTrue(self.app.card_scroll.winfo_ismapped())
        self.shot("14-compacto")
        self.app.geometry("1366x768")
        self.pump(.8)
        self.assertFalse(self.app.compact)
        self.assertEqual(self.app._columns, 4)

    def test_15_minimize_pauses_animation(self):
        # Sem gerenciador de janelas o Xvfb não minimiza; simula o estado informado pelo sistema.
        from unittest.mock import patch
        calls = []
        card = next(iter(self.app.cards.values()))
        with patch.object(self.app, "state", return_value="iconic"), \
                patch.object(card, "animate", side_effect=lambda phase: calls.append(phase)):
            self.pump(.5)
        self.assertEqual(calls, [], "minimizado não anima")
        with patch.object(card, "animate", side_effect=lambda phase: calls.append(phase)):
            self.pump(.5)
        self.assertTrue(calls, "visível volta a animar")

    def test_16_version_only_in_footer(self):
        def texts(widget):
            found = []
            for child in widget.winfo_children():
                try:
                    found.append(str(child.cget("text")))
                except tk.TclError:
                    pass
                found += texts(child)
            return found
        from hipauto import __version__
        self.assertEqual([t for t in texts(self.app) if __version__ in t], [f"v{__version__}"])

    def test_99_window_close(self):
        self.app.tk.call(self.app.protocol("WM_DELETE_WINDOW"))  # mesmo caminho do botão fechar da janela
        self.assertFalse(self.app._alive)


class CommandLine(unittest.TestCase):
    """Opções de linha de comando, no código-fonte e no executável publicado."""

    TARGETS = [[sys.executable, str(ROOT / "hipauto_desktop.py")]]
    if (ROOT / "dist" / "HIPAUTO-Desktop").exists():
        TARGETS.append([str(ROOT / "dist" / "HIPAUTO-Desktop")])

    def run_cli(self, target, *args, timeout=90):
        env = dict(os.environ)
        env.pop("DISPLAY", None)  # as opções de linha de comando não podem depender de tela
        return subprocess.run(target + list(args), capture_output=True, text=True, timeout=timeout, env=env)

    def test_version(self):
        from hipauto import __version__
        for target in self.TARGETS:
            with self.subTest(target[-1]):
                self.assertEqual(self.run_cli(target, "--version").stdout.strip(), __version__)

    def test_report_and_report_with_tests(self):
        for target in self.TARGETS:
            with self.subTest(target[-1]):
                plain = json.loads(self.run_cli(target, "--report").stdout)
                self.assertEqual(len(plain["devices"]), 11)
                self.assertEqual(plain["testResults"], {})
                tested = json.loads(self.run_cli(target, "--report", "--test").stdout)
                self.assertEqual(len(tested["testResults"]), 11)
                self.assertEqual(tested["testResults"]["serial:ttyS0"]["weight"], "1.235 kg")

    def test_smak_probe_never_opens_the_interface(self):
        for target in self.TARGETS:
            with self.subTest(target[-1]):
                started = time.monotonic()
                completed = self.run_cli(target, "--smak-probe", timeout=30)
                self.assertLess(time.monotonic() - started, 30)
                self.assertNotIn("Traceback", completed.stderr)


if __name__ == "__main__":
    unittest.main()

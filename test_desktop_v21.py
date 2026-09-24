import time
import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import patch

import hipauto_desktop as base
import hipauto_desktop_v21 as desktop


DEVICE = {"id": "scale:1", "category": "scale", "name": "Balança P05",
          "connection": "Serial", "port": "/dev/ttyUSB0", "status": "detected",
          "detail": "Aguardando teste"}


class SimplifiedDesktopTests(unittest.TestCase):
    def setUp(self):
        self.discover = patch.object(base.engine, "discover", return_value=[DEVICE.copy()])
        self.messages = patch.object(base.messagebox, "showinfo")
        self.discover.start(); self.messages.start()
        self.app = desktop.HipautoDesktop()
        self.wait_until(lambda: len(self.app.devices) == 1)

    def tearDown(self):
        self.app.destroy(); self.messages.stop(); self.discover.stop()

    def wait_until(self, condition, timeout=3):
        end = time.monotonic() + timeout
        expired = [False]
        def poll():
            if condition(): self.app.quit()
            elif time.monotonic() >= end: expired[0] = True; self.app.quit()
            else: self.app.after(10, poll)
        self.app.after(0, poll); self.app.mainloop()
        if expired[0]: self.fail("Operação não terminou no prazo")

    def test_removed_actions_are_not_visible(self):
        toolbar = self.app.refresh_button.master
        self.assertFalse(any(isinstance(item, ttk.Entry) for item in toolbar.winfo_children()))
        texts = [item.cget("text") for item in toolbar.winfo_children()
                 if isinstance(item, (ttk.Button, tk.Label))]
        self.assertNotIn("Buscar:", texts)
        self.assertNotIn("Exportar relatório", texts)
        self.assertIn("Atualizar", texts)
        self.assertIn("Testar todos", texts)

    def test_core_actions_remain_functional(self):
        self.app.tree.selection_set("scale:1")
        with patch.object(base.engine, "test_device", return_value={"status": "ok", "detail": "Acessível"}):
            self.app.test_selected(); self.wait_until(lambda: not self.app.busy)
        self.assertEqual(self.app.results["scale:1"]["status"], "ok")


if __name__ == "__main__": unittest.main()

import time
import tkinter as tk
import unittest
from unittest.mock import patch

import hipauto_desktop_v23 as desktop
import hipauto_desktop_release_v23

DEVICE={"id":"scale:1","category":"scale","name":"Balança P05","connection":"Serial",
        "port":"/dev/ttyUSB0","status":"ok","detail":"Peso recebido","driver":"serial_core"}


class CardInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.discovery=patch.object(desktop.engine,"discover",return_value=[DEVICE.copy()]);self.discovery.start()
        self.app=desktop.HipautoDesktop();self.wait_until(lambda:len(self.app.devices)==1 and not self.app.busy)

    def tearDown(self):self.app.destroy();self.discovery.stop()

    def wait_until(self,condition,timeout=3):
        end=time.monotonic()+timeout;expired=[False]
        def poll():
            if condition():self.app.quit()
            elif time.monotonic()>=end:expired[0]=True;self.app.quit()
            else:self.app.after(10,poll)
        self.app.after(0,poll);self.app.mainloop()
        if expired[0]:self.fail("Interface não respondeu no prazo")

    def test_card_and_summary_are_rendered(self):
        self.assertEqual(len(self.app.cards),1);self.assertTrue(self.app.cards["scale:1"][2])
        self.assertEqual(self.app.tree.item("scale:1","values")[1],"/dev/ttyUSB0")

    def test_card_opens_two_column_detail_modal(self):
        self.app.open_details(self.app.devices[0]);self.app.update()
        modal=next(child for child in self.app.winfo_children() if isinstance(child,tk.Toplevel))
        body=next(child for child in modal.winfo_children()
                  if isinstance(child,tk.Frame) and child.cget("bg")==desktop.SURFACE)
        labels=[child for child in body.winfo_children() if isinstance(child,tk.Label)]
        self.assertGreaterEqual(len(labels),10)
        self.assertEqual({int(label.grid_info()["column"]) for label in labels},{0,1})
        modal.destroy()


if __name__=="__main__":unittest.main()

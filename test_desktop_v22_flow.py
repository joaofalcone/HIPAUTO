import time
import tkinter as tk
import unittest
from unittest.mock import patch

import hipauto_desktop as base
import hipauto_desktop_v22 as desktop


class VersionPlacementTests(unittest.TestCase):
    def test_version_exists_only_in_footer(self):
        with patch.object(base.engine, "discover", return_value=[]):
            app = desktop.HipautoDesktop()
            expired = [False]
            end = time.monotonic() + 3
            def poll():
                if not app.busy: app.quit()
                elif time.monotonic() >= end: expired[0] = True; app.quit()
                else: app.after(10, poll)
            app.after(0, poll); app.mainloop()
        try:
            self.assertFalse(expired[0])
            footer = app.test_button.master
            footer_texts = [item.cget("text") for item in footer.winfo_children()
                            if isinstance(item, tk.Label)]
            self.assertIn(" v22.0 ", footer_texts)
            header = app.winfo_children()[0]
            header_texts = []
            for item in header.winfo_children():
                if isinstance(item, tk.Frame):
                    header_texts.extend(child.cget("text") for child in item.winfo_children()
                                        if isinstance(child, tk.Label))
            self.assertNotIn("22.0", " ".join(header_texts))
        finally: app.destroy()


if __name__ == "__main__": unittest.main()

import os
import pty
import threading
import unittest
from unittest.mock import patch

import hipauto_v18 as app


class ScaleP05Tests(unittest.TestCase):
    def test_decode_zero_weight(self):
        self.assertEqual(app.decode_p05(b"\x0200000\x03")["weight"], "0 kg")

    def test_decode_decimal_weight(self):
        self.assertEqual(app.decode_p05(b"\x0214385\x03")["weight"], "14.385 kg")

    def test_rejects_unframed_digits(self):
        self.assertIsNone(app.decode_p05(b"00000"))

    def test_real_serial_exchange(self):
        master, slave = pty.openpty(); port = os.ttyname(slave)
        def responder():
            if os.read(master, 1) == b"\x05": os.write(master, b"\x0200000\x03")
        thread = threading.Thread(target=responder); thread.start()
        result = app.probe_p05(port, 1.0); thread.join(1)
        os.close(master); os.close(slave)
        self.assertTrue(result["matched"])
        self.assertEqual(result["decoded"]["weight"], "0 kg")

    def test_discovery_promotes_only_valid_response(self):
        device={"id":"serial:ttyS4","category":"unknown","name":"Serial","connection":"Serial",
                "port":"/dev/ttyS4","evidence":[],"port_details":{}}
        with patch.object(app,"BASE_DISCOVER",return_value=[device]), patch.object(app.Path,"exists",return_value=True), \
             patch.object(app,"port_is_busy",return_value=False), patch.object(app,"probe_p05",return_value={
                 "matched":True,"hex":"02 30 30 30 30 30 03","decoded":{"kind":"weight","payload":"00000","weight":"0 kg"}}):
            found=app.discover()[0]
        self.assertEqual(found["category"],"scale")
        self.assertEqual(found["scale_protocol"],"P05 compatível")

if __name__ == "__main__": unittest.main()

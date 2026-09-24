#!/usr/bin/env python3
"""HIPAUTO V15 - identificacao SMAK consistente em coleta, testes e relatorio."""
import sys
import time
from urllib.parse import urlparse

import hipauto_v14 as v14

core = v14.core


def report(run_tests=False):
    devices = v14.discover()
    results = {}
    if run_tests:
        for device in devices:
            try:
                tested = core.test_device(device)
            except Exception as exc:
                tested = {"status": "error", "detail": str(exc)}
            results[device["id"]] = tested
            device.update(tested)
    environment = v14.v13.v12.v11.v10.v9.v8.v7.v6.v5.environment()
    recommendations = v14.v13.v12.v11.v10.v9.v8.v7.v6.v5.recommendations(devices, environment)
    return {"schemaVersion": 5, "appVersion": "15.0", "environment": environment,
            "devices": devices, "recommendations": recommendations, "testResults": results}


class Handler(v14.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json({"ok": True, "version": "15.0", "platform": "Ubuntu Desktop",
                              "smakProbe": "isolated-read-only"})
        if path == "/api/report":
            return self.json(report(False))
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == "/api/test-all":
            return self.json(report(True))
        return super().do_POST()


core.Handler = Handler

if __name__ == "__main__":
    if "--smak-probe" in sys.argv:
        v14.probe_smak_worker()
    else:
        core.main()

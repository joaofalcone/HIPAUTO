"""Relatório JSON para suporte (linha de comando, sem interface)."""

from __future__ import annotations

from typing import Any

from . import __version__, checks, discovery, environment


def build(run_tests: bool = False) -> dict[str, Any]:
    devices = discovery.discover()
    results = {device["id"]: checks.test_device(device) for device in devices} if run_tests else {}
    env = environment.snapshot()
    return {"schemaVersion": 7, "appVersion": __version__, "environment": env, "devices": devices,
            "recommendations": environment.recommendations(devices, env), "testResults": results}

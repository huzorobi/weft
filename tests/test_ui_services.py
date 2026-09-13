"""UI restart-services helper."""
from __future__ import annotations

from weft.ui import services


class _R:
    def __init__(self, rc, out): self.returncode = rc; self.stdout = out


def test_restart_services_success(monkeypatch):
    monkeypatch.setattr(services.subprocess, "run",
                        lambda *a, **k: _R(0, "→ starting…\n→ Ollama ready (model llama3.2:3b)\n"))
    ok, msg = services.restart_services()
    assert ok is True and "Ollama ready" in msg


def test_restart_services_failure(monkeypatch):
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: _R(1, "boom\n"))
    ok, msg = services.restart_services()
    assert ok is False and msg == "boom"


def test_restart_services_timeout(monkeypatch):
    def boom(*a, **k): raise services.subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(services.subprocess, "run", boom)
    ok, msg = services.restart_services()
    assert ok is False and "timed out" in msg

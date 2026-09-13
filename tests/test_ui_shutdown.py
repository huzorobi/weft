"""UI shutdown helper — command construction + repo-root resolution (no actual shutdown)."""
from __future__ import annotations

from pathlib import Path

from weft.ui import shutdown


def test_repo_root_points_at_weft_sh():
    root = shutdown.repo_root()
    assert (root / "weft.sh").exists()          # the launcher lives at the repo root
    assert (root / "src" / "weft").is_dir()


def test_build_command_calls_launcher_stop_after_delay():
    cmd = shutdown.build_command(2.0, script=Path("/tmp/weft.sh"))
    assert cmd.startswith("sleep 2.0;")
    assert "exec /tmp/weft.sh --stop" in cmd


def test_request_shutdown_is_detached(monkeypatch):
    captured = {}
    class FakePopen:
        def __init__(self, args, **kw): captured["args"] = args; captured["kw"] = kw
    monkeypatch.setattr(shutdown.subprocess, "Popen", FakePopen)
    shutdown.request_shutdown(0.1)
    assert captured["args"][0] == "bash" and captured["args"][1] == "-c"
    assert "--stop" in captured["args"][2]
    assert captured["kw"]["start_new_session"] is True   # survives the UI being killed

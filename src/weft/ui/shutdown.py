"""Shut Weft down from the UI.

Stops the whole run: the self-hosted stack (Neo4j, SearXNG, Tor) and the Streamlit UI itself,
by handing off to the launcher's ``weft.sh --stop`` in a detached process after a short delay —
so the UI can render a goodbye message before it is killed. Ollama is left running (it is often
a shared service; the launcher leaves it too).
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


def repo_root() -> Path:
    # this file is src/weft/ui/shutdown.py -> parents: ui, weft, src, <repo root>
    return Path(__file__).resolve().parents[3]


def build_command(delay: float = 1.5, *, script: Path | None = None) -> str:
    script = script or (repo_root() / "weft.sh")
    return f"sleep {float(delay)}; exec {shlex.quote(str(script))} --stop"


def request_shutdown(delay: float = 1.5) -> None:
    """Detached: after ``delay`` seconds, stop the stack and the UI via the launcher."""
    subprocess.Popen(
        ["bash", "-c", build_command(delay)],
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

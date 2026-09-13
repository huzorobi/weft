"""Start the self-hosted services from the UI.

Backs the sidebar's "Restart services" button by running the launcher's ``weft.sh --services``,
which brings up the stack (Neo4j, SearXNG, Tor) and the local AI without touching the UI. Runs
synchronously so the caller can refresh the status dots once it returns.
"""
from __future__ import annotations

import subprocess

from weft.ui.shutdown import repo_root


def restart_services(timeout: float = 180.0) -> tuple[bool, str]:
    """Bring the services up; return (ok, last-line-of-output)."""
    script = repo_root() / "weft.sh"
    try:
        r = subprocess.run(
            ["bash", str(script), "--services"],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out waiting for services to start"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{type(exc).__name__}: {exc}"
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    return r.returncode == 0, (lines[-1] if lines else "services started")

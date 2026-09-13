"""Live service-status checks for the UI status panel.

Cheap TCP reachability checks for the self-hosted services and the local AI, so the sidebar can
show a green dot when each is live and a red one when it is not. Pure (only opens sockets).
"""
from __future__ import annotations

import socket

# (display name, port) — the services a full Weft run relies on.
SERVICES = [("Neo4j", 7687), ("SearXNG", 8080), ("Tor", 9050), ("Ollama", 11434)]


def port_open(port: int, *, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def service_status() -> dict[str, bool]:
    """Name -> is-reachable, for each service."""
    return {name: port_open(port) for name, port in SERVICES}


def all_live(status: dict[str, bool] | None = None) -> bool:
    status = status if status is not None else service_status()
    return bool(status) and all(status.values())

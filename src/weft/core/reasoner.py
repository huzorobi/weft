"""The reasoning abstraction — a local LLM that reasons ABOUT evidence.

The model never produces findings; it narrates and summarises the deterministic graph
the modules already built. It is optional (Weft works fully without it) and local-only
(personal data must not leave the estate — sending names and emails to a hosted model
is itself a data-transfer problem), so the only shipped backend talks to a local
Ollama. Swap the backend by injecting a different :class:`Reasoner`.

Keep prompts grounded in the supplied facts; the caller is responsible for discarding
any narrative that asserts something the graph does not support.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Reasoner(Protocol):
    @property
    def available(self) -> bool: ...
    def narrate(self, *, system: str, prompt: str) -> str: ...


class NullReasoner:
    """No LLM. Weft falls back to a purely deterministic report."""

    name = "none"

    @property
    def available(self) -> bool:
        return False

    def narrate(self, *, system: str, prompt: str) -> str:
        return ""


class OllamaReasoner:
    """Local Ollama backend. Small models (3B-8B) are plenty for narration on an 8GB GPU.

    Talks only to a local Ollama HTTP endpoint (default localhost:11434). ``available``
    checks the daemon is up and the model is pulled, so a report degrades to the
    deterministic sections rather than erroring when the model is missing.
    """

    def __init__(self, model: str = "llama3.2:3b", *, base_url: str = "http://localhost:11434",
                 timeout: float = 120.0, temperature: float = 0.2):
        self.model = model
        self.name = f"ollama:{model}"
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._temperature = temperature

    @property
    def available(self) -> bool:
        try:
            import httpx

            r = httpx.get(f"{self._base}/api/tags", timeout=5.0)
            if r.status_code != 200:
                return False
            names = {m.get("name", "") for m in r.json().get("models", [])}
            # accept an exact match or the base name (model may carry a :tag)
            return self.model in names or any(n.split(":")[0] == self.model.split(":")[0] for n in names)
        except Exception:
            return False

    def narrate(self, *, system: str, prompt: str) -> str:
        try:
            import httpx

            r = httpx.post(
                f"{self._base}/api/generate",
                json={"model": self.model, "system": system, "prompt": prompt,
                      "stream": False, "options": {"temperature": self._temperature}},
                timeout=self._timeout,
            )
            if r.status_code != 200:
                return ""
            return (r.json().get("response") or "").strip()
        except Exception:
            return ""

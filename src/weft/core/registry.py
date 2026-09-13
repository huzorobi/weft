"""Module registry and discovery.

Modules register themselves with the ``@register`` decorator, so adding a source is
copy-and-fill with no central import list to edit. ``discover()`` imports every
submodule under ``weft.modules`` so those decorators run, then ``instances()`` builds
one instance of each registered module.
"""
from __future__ import annotations

import importlib
import pkgutil

from weft.core.module import Module

_REGISTRY: dict[str, type[Module]] = {}


def register(cls: type[Module]) -> type[Module]:
    """Class decorator: register a module by its ``name``."""
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError(f"{cls.__name__} must set a non-empty 'name' to be registered")
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(f"duplicate module name '{name}' ({cls.__name__} vs {_REGISTRY[name].__name__})")
    _REGISTRY[name] = cls
    return cls


def discover() -> None:
    """Import all submodules under ``weft.modules`` to trigger registration."""
    import weft.modules as pkg

    for mod in pkgutil.walk_packages(pkg.__path__, prefix=pkg.__name__ + "."):
        importlib.import_module(mod.name)


def registered_classes() -> dict[str, type[Module]]:
    return dict(_REGISTRY)


def instances() -> list[Module]:
    """Instantiate every registered module. Call ``discover()`` first."""
    return [cls() for cls in _REGISTRY.values()]


def clear() -> None:
    """Reset the registry (tests only)."""
    _REGISTRY.clear()

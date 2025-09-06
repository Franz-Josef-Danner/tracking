"""UI package for Kaiserlich Tracker."""
import importlib

from . import utils as _utils  # noqa: F401  # re-export
from . import solve_log as _solve_log  # noqa: F401  # provides functions

_MODULES = []
for _name in ("overlay", "menus", "panels"):
    try:
        _MODULES.append(importlib.import_module(f".{_name}", __name__))
    except Exception:
        pass


def register():
    for m in _MODULES:
        if hasattr(m, "register"):
            m.register()


def unregister():
    for m in reversed(_MODULES):
        if hasattr(m, "unregister"):
            try:
                m.unregister()
            except Exception:
                pass


from __future__ import annotations
import bpy

BUSY_KEY = "__refine_busy"

def set_busy(state: bool) -> None:
    """Markiert eine kritische Sektion (z. B. Refine‑Loop) als 'busy'.
    Andere Timer/Modal‑Operatoren sollen währenddessen pausieren."""
    try:
        bpy.context.scene[BUSY_KEY] = bool(state)
    except Exception:
        pass

def is_busy() -> bool:
    """Abfrage: ist aktuell eine kritische Sektion aktiv?"""
    try:
        return bool(bpy.context.scene.get(BUSY_KEY, False))
    except Exception:
        return False

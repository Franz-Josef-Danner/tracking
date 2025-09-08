# SPDX-License-Identifier: GPL-2.0-or-later
"""Helper/__init__.py – Reduziert: keine Auto-Registrierung, keine toten Exporte.
   Hintergrund: Fokus auf distanze.py; Detect-only Variante vermeidet Abhängigkeiten."""
from __future__ import annotations

__all__ = ("register", "unregister")

def register() -> None:
    # bewusst leer
    return

def unregister() -> None:
    # bewusst leer
    return

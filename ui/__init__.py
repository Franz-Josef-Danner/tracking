# SPDX-License-Identifier: GPL-2.0-or-later
# Kaiserlich UI bootstrap – nur noch Repeat-Scope (+ optionale UI-Module), Alt-Overlay wird aktiv bereinigt.
import sys
import importlib

# Nur die heute genutzten UI-Module:
try:
    from . import repeat_scope  # Draw-Handler für Repeat-Zähler
except Exception as e:
    repeat_scope = None
    print(f"[UI] repeat_scope import failed: {e!r}")

try:
    from . import solve_log  # falls vorhanden; optional
except Exception:
    solve_log = None


def _purge_legacy_overlay_handlers():
    """Räumt etwaige Alt-Overlay-Handler und Module robust ab, falls noch im Speicher."""
    candidates = [
        f"{__package__}.overlay",
        f"{__package__}.overlay_impl",
        # historische Varianten (zur Sicherheit):
        f"{__package__}.legacy_overlay",
    ]
    for name in candidates:
        mod = sys.modules.get(name)
        if not mod:
            continue
        # Mögliche Deaktivierungsfunktionen durchprobieren:
        for attr in ("disable_overlay_handler", "disable_repeat_scope_handler", "disable_handler", "unregister", "remove_handler"):
            fn = getattr(mod, attr, None)
            if callable(fn):
                try:
                    fn()
                    print(f"[LegacyOverlay] {name}.{attr}() → OK")
                except Exception as e:
                    print(f"[LegacyOverlay][WARN] {name}.{attr}() failed: {e!r}")
        # Modul entfernen
        sys.modules.pop(name, None)
        print(f"[LegacyOverlay] purged module: {name}")


def register():
    _purge_legacy_overlay_handlers()
    # repeat_scope ist der einzige verbleibende Overlay-Pfad
    if repeat_scope and hasattr(repeat_scope, "register"):
        try:
            repeat_scope.register()
        except Exception as e:
            print(f"[UI] repeat_scope.register failed: {e!r}")
    if solve_log and hasattr(solve_log, "register"):
        try:
            solve_log.register()
        except Exception as e:
            print(f"[UI] solve_log.register failed: {e!r}")
    print("[UI] registered – legacy overlay removed")


def unregister():
    # Reihenfolge invers
    if solve_log and hasattr(solve_log, "unregister"):
        try:
            solve_log.unregister()
        except Exception as e:
            print(f"[UI] solve_log.unregister failed: {e!r}")
    if repeat_scope and hasattr(repeat_scope, "unregister"):
        try:
            repeat_scope.unregister()
        except Exception as e:
            print(f"[UI] repeat_scope.unregister failed: {e!r}")
    _purge_legacy_overlay_handlers()
    print("[UI] unregistered – legacy overlay removed")

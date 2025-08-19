# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py

Minimaler Coordinator: ruft **ausschließlich** den Track‑Helper‑Operator
`bw.track_to_scene_end` auf (vorwärts tracken bis **Szenenende**),
initial mit `INVOKE_DEFAULT`.

Fixes:
- Behebt SyntaxError durch doppelte Vererbung in der Klassendefinition.
- Registriert den Helper‑Operator on‑the‑fly, falls noch nicht registriert.
- Robustere Importstrategie für unterschiedliche Paket‑Layouts.
- Leichte Self‑Tests (nicht modal, sicher in Headless‑Runs).
"""
from __future__ import annotations

import bpy
from typing import Set, Optional
from importlib import import_module

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# ------------------------------------------------------------
# Import/Registration des Track‑Operators (bw.track_to_scene_end)
# ------------------------------------------------------------
_BW_OP = None  # type: Optional[type]


def _try_import_candidates() -> Optional[type]:
    """Versucht die Operator‑Klasse `BW_OT_track_to_scene_end` zu importieren.

    Unterstützt typische Layouts:
    - Paket/Helper/tracking_helper.py  →  ..Helper.tracking_helper
    - Paket/tracking_helper.py         →  ..tracking_helper
    - Direkt importierbar              →  tracking_helper
    """
    candidates = (
        ("..Helper.tracking_helper", True),
        ("..tracking_helper", True),
        ("tracking_helper", False),
    )
    for name, is_rel in candidates:
        try:
            mod = import_module(name, package=__package__) if is_rel else import_module(name)
            op = getattr(mod, "BW_OT_track_to_scene_end", None)
            if op is not None:
                return op
        except Exception:
            # still try next candidate
            pass
    return None


def _ensure_bw_op_registered() -> None:
    """Importiert und registriert `BW_OT_track_to_scene_end` wenn nötig."""
    global _BW_OP
    if _BW_OP is None:
        _BW_OP = _try_import_candidates()
    if _BW_OP is None:
        raise RuntimeError(
            "Konnte BW_OT_track_to_scene_end nicht importieren. Prüfe, ob 'tracking_helper.py' "
            "im Paket liegt (Helper/tracking_helper.py oder tracking_helper.py) und die Klasse enthält."
        )
    try:
        bpy.utils.register_class(_BW_OP)
    except ValueError:
        # Bereits registriert → ok
        pass


# ------------------------------------------------------------
# Operator (Coordinator) – korrigierte Vererbung
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Startet nur den Track‑Helper (vorwärts bis Szenenende)."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Track to Scene End)"
    bl_description = (
        "Startet den Track‑Helper: vorwärts tracken bis zum Szenenende."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Minimal: Nur im Clip‑Editor verfügbar (verhindert falschen Kontext).
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            _ensure_bw_op_registered()
            # UI‑konformer Aufruf
            bpy.ops.bw.track_to_scene_end('INVOKE_DEFAULT')
            return {"FINISHED"}
        except Exception as ex:
            self.report({'ERROR'}, f"Track-Helper-Fehler: {ex}")
            return {"CANCELLED"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Spiegelung für Scripting
        return self.invoke(context, None)


# ----------
# Register
# ----------
_classes = (CLIP_OT_tracking_coordinator,)


def register():
    for c in _classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass
    print("[Coordinator] registered (Track‑Helper only)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")


# ------------------------------------------------------------
# Light Self‑Tests (werden nur ausgeführt, wenn als Script gestartet)
# ------------------------------------------------------------

def _selftest_registration_only() -> None:
    """Nicht‑modaler Mini‑Test: Registrierung/Abmeldung & Idnames prüfen.

    Dieser Test ruft **nicht** den eigentlichen Tracking‑Operator auf und
    benötigt daher keinen CLIP_EDITOR‑Kontext. Sicher in Headless/CI.
    """
    # 1) Ensure helper class importierbar
    op_cls = _try_import_candidates()
    assert op_cls is not None, "BW_OT_track_to_scene_end nicht importierbar"
    assert getattr(op_cls, 'bl_idname', '') == 'bw.track_to_scene_end', (
        "Unerwarteter bl_idname der Helper‑Klasse"
    )

    # 2) Coordinator registrieren/abmelden
    register()
    assert hasattr(bpy.ops, 'clip'), "bpy.ops.clip nicht verfügbar"
    # poll sollte False liefern können (je nach Kontext), aber Klasse existiert
    assert CLIP_OT_tracking_coordinator.bl_idname == 'clip.tracking_coordinator'
    unregister()


if __name__ == "__main__":
    # Nur einfache, sichere Checks ausführen
    _selftest_registration_only()

# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – robuste, importlose Fallback-Variante

Ziel:
- **Kein** scheitern mehr an Importpfaden. Wir versuchen zuerst, den Operator
  `bw.track_to_scene_end` direkt zu benutzen. Wenn er fehlt, registrieren wir
  ihn über den Helper-Registrar, und als letzte Option direkt über die Klasse.
- Start weiterhin mit **INVOKE_DEFAULT**, warten **modal** auf WM-Token, dann
  "Finish".
"""
from __future__ import annotations

from importlib import import_module
from time import time_ns, monotonic
from typing import Optional, Set

import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

TIMEOUT_SEC = 30.0  # optionales Timeout, damit der Modal-Loop nie ewig hängt


# ---------------------------------------------------------------------------
# Operator-Verfügbarkeit sicherstellen
# ---------------------------------------------------------------------------

def _op_available() -> bool:
    try:
        # Zugriff auf Unter-Namespace kann AttributeError werfen, wenn 'bw' nicht existiert
        return hasattr(bpy.ops, "bw") and hasattr(bpy.ops.bw, "track_to_scene_end")
    except Exception:
        return False


def _ensure_operator_available() -> None:
    """Sorgt dafür, dass `bw.track_to_scene_end` registriert ist.

    Reihenfolge:
    1) Wenn vorhanden → fertig
    2) Helper-Registrar (`..Helper.register`) versuchen
    3) Direkten Klassenimport (`..Helper.tracking_helper.BW_OT_track_to_scene_end`) und
       Registrierung versuchen
    4) Als Fallback auch absolute Importe probieren
    """
    if _op_available():
        return

    # (2) Versuche den Helper-Registrar aufzurufen
    try:
        # relativ aus Nachbarpaket
        from ..Helper import register as _reg_helper  # type: ignore
        _reg_helper()
    except Exception:
        # Best effort: vielleicht existiert nur das Modul
        pass

    if _op_available():
        return

    # (3) Direkte Klassenregistrierung versuchen
    last_ex = None
    for modname, is_rel in (("..Helper.tracking_helper", True), ("Helper.tracking_helper", False), ("tracking_helper", False)):
        try:
            mod = import_module(modname, package=__package__) if is_rel else import_module(modname)
            cls = getattr(mod, "BW_OT_track_to_scene_end", None)
            if cls is None:
                continue
            try:
                bpy.utils.register_class(cls)
            except ValueError:
                # bereits registriert
                pass
            break
        except Exception as ex:  # speichere letzte Ausnahme zur Fehlermeldung
            last_ex = ex
    if not _op_available():
        raise RuntimeError(
            "Operator 'bw.track_to_scene_end' nicht verfügbar. Prüfe Paketstruktur:"
            " <AddonRoot>/Helper/__init__.py, <AddonRoot>/Helper/tracking_helper.py und"
            " <AddonRoot>/Operator/__init__.py müssen existieren."
        ) from last_ex


# ---------------------------------------------------------------------------
# Modal-Operator
# ---------------------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (wait for Helper)"
    bl_description = (
        "Startet bw.track_to_scene_end (Forward, Sequence) und wartet auf Feedback, bevor 'Finish' gemeldet wird."
    )
    bl_options = {"REGISTER"}

    _token: Optional[str] = None
    _timer: Optional[object] = None
    _deadline: Optional[float] = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            _ensure_operator_available()
        except Exception as ex:
            self.report({'ERROR'}, f"Track-Helper-Setup fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        wm = context.window_manager
        self._token = str(time_ns())
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass

        # Helper starten (INVOKE_DEFAULT)
        try:
            ret = bpy.ops.bw.track_to_scene_end('INVOKE_DEFAULT', coord_token=self._token)
            if ret and 'CANCELLED' in ret:
                self.report({'ERROR'}, "Helper wurde abgebrochen (kein Clip/keine Marker?)")
                return {"CANCELLED"}
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Start fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        # Modal warten
        self._deadline = monotonic() + TIMEOUT_SEC
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        if event.type == 'ESC':
            return self._finish(context, cancelled=True, msg="Abgebrochen (ESC)")

        if event.type == 'TIMER':
            # Timeout prüfen
            if self._deadline is not None and monotonic() > self._deadline:
                return self._finish(context, cancelled=True, msg="Timeout (kein Feedback vom Helper)")

            wm = context.window_manager
            done = wm.get("bw_tracking_done_token", "")
            if done and self._token and done == self._token:
                info = wm.get("bw_tracking_last_info")
                if info:
                    self.report({'INFO'}, f"Tracking done: start={info.get('start_frame')} → {info.get('tracked_until')}")
                return self._finish(context, cancelled=False, msg="Finish")
        return {"RUNNING_MODAL"}

    def _finish(self, context: bpy.types.Context, *, cancelled: bool, msg: str) -> Set[str]:
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass
        self._token = None
        self._deadline = None
        if cancelled:
            self.report({'WARNING'}, msg)
            return {"CANCELLED"}
        else:
            self.report({'INFO'}, msg)
            return {"FINISHED"}


_classes = (CLIP_OT_tracking_coordinator,)


def register():
    for c in _classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass
    print("[Coordinator] registered (importless fallback)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")

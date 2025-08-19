# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py

Coordinator ruft **ausschließlich** den Track‑Helper‑Operator
`bw.track_to_scene_end` mit `INVOKE_DEFAULT` auf, **wartet modal** auf dessen
Feedback (Token in WindowManager) und gibt erst dann "Finish" aus.

Eigenschaften:
- Robust: importiert/registriert den Helper on‑the‑fly aus üblichen Paket‑Layouts
- Synchronisations‑Token: wm["bw_tracking_done_token"] == token
- Aufräumen: Timer entfernen, Token leeren
- Kontext: ausschließlich im CLIP_EDITOR aufrufbar
"""
from __future__ import annotations

from importlib import import_module
from time import time_ns
from typing import Optional, Set

import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

# ------------------------------------------------------------
# Import/Registration des Track‑Operators (bw.track_to_scene_end)
# ------------------------------------------------------------
_BW_OP: Optional[type] = None


def _try_import_candidates() -> Optional[type]:
    """Sucht nach BW_OT_track_to_scene_end in gängigen Modulpfaden."""
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
            pass
    return None


def _ensure_bw_op_registered() -> None:
    global _BW_OP
    if _BW_OP is None:
        _BW_OP = _try_import_candidates()
    if _BW_OP is None:
        raise RuntimeError(
            "Konnte BW_OT_track_to_scene_end nicht importieren. Liegt 'tracking_helper.py' im Paket?"
        )
    try:
        bpy.utils.register_class(_BW_OP)
    except ValueError:
        # bereits registriert
        pass


# ------------------------------------------------------------
# Operator (Coordinator) – wartet modal auf Helper‑Feedback
# ------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Startet den Track‑Helper und wartet auf Rückmeldung, dann "Finish"."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (wait for Helper)"
    bl_description = (
        "Startet bw.track_to_scene_end (Forward, Sequence) und wartet auf Feedback, bevor 'Finish' gemeldet wird."
    )
    bl_options = {"REGISTER"}

    _token: Optional[str] = None
    _timer: Optional[object] = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    # ----- Lifecycle -----
    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            _ensure_bw_op_registered()
        except Exception as ex:
            self.report({'ERROR'}, f"Track-Helper-Import fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        wm = context.window_manager
        self._token = str(time_ns())
        # erwarteten Slot leeren
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass

        # Helper mit Token starten (INVOKE_DEFAULT)
        try:
            bpy.ops.bw.track_to_scene_end('INVOKE_DEFAULT', coord_token=self._token)
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Start fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        # Modal‑Timer anwerfen und warten
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        if event.type == 'ESC':
            return self._finish(context, cancelled=True, msg="Abgebrochen (ESC)")

        if event.type == 'TIMER':
            wm = context.window_manager
            done = wm.get("bw_tracking_done_token", "")
            if done and self._token and done == self._token:
                # Optional: Infos vom Helper lesen und loggen
                info = wm.get("bw_tracking_last_info")
                if info:
                    self.report({'INFO'}, f"Tracking done: start={info.get('start_frame')} → {info.get('tracked_until')}")
                return self._finish(context, cancelled=False, msg="Finish")
        return {"RUNNING_MODAL"}

    # ----- Helpers -----
    def _finish(self, context: bpy.types.Context, *, cancelled: bool, msg: str) -> Set[str]:
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        # Token aufräumen (nicht zwingend nötig, aber sauber)
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass
        self._token = None
        if cancelled:
            self.report({'WARNING'}, msg)
            return {"CANCELLED"}
        else:
            self.report({'INFO'}, msg)
            return {"FINISHED"}


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
    print("[Coordinator] registered (modal wait for Helper)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")

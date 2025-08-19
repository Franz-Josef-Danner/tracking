# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – robuste Variante (erzwingt Helper-Registration)

- Startet `bw.track_to_scene_end` mit **INVOKE_DEFAULT**.
- **Registriert den Helper-Operator immer aktiv**, statt nur zu prüfen, ob
  er existiert (hasattr-Checks sind bei bpy.ops trügerisch).
- **Wartet modal** auf WindowManager-Token, optionales Timeout.
"""
from __future__ import annotations

from importlib import import_module
from time import time_ns, monotonic
from typing import Optional, Set, Type

import bpy

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

TIMEOUT_SEC = 30.0

# ---------------------------------------------------------------------------
# Helper-Klasse importieren & REGISTRIEREN (erzwingen)
# ---------------------------------------------------------------------------

def _import_helper_class() -> Type[bpy.types.Operator]:
    last_ex: Exception | None = None
    for modname, is_rel in (
        ("..Helper.tracking_helper", True),
        ("..tracking_helper", True),
        ("tracking_helper", False),
    ):
        try:
            mod = import_module(modname, package=__package__) if is_rel else import_module(modname)
            cls = getattr(mod, "BW_OT_track_to_scene_end", None)
            if cls is not None:
                return cls
        except Exception as ex:
            last_ex = ex
    raise RuntimeError(
        "Konnte Klasse BW_OT_track_to_scene_end nicht importieren. Prüfe Paketstruktur:"
        " <AddonRoot>/Helper/tracking_helper.py (mit Operator-Klasse) und __init__.py."
    ) from last_ex


def _ensure_registered() -> None:
    cls = _import_helper_class()
    try:
        bpy.utils.register_class(cls)
    except ValueError:
        # Bereits registriert → ok
        pass


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
        # **Immer** versuchen, den Helper zu registrieren (sicherer als hasattr-Checks)
        try:
            _ensure_registered()
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
            # Optional: Presence-Check via poll() – gibt False zurück, wenn Kontext falsch ist
            poll_ok = False
            try:
                poll_ok = bool(bpy.ops.bw.track_to_scene_end.poll())
            except Exception:
                # poll() ggf. nicht verfügbar – ignorieren und versuchen zu starten
                pass

            ret = bpy.ops.bw.track_to_scene_end('INVOKE_DEFAULT', coord_token=self._token)
            if ret and 'CANCELLED' in ret:
                self.report({'ERROR'}, "Helper wurde abgebrochen (kein Clip/keine Marker/kein CLIP_EDITOR?)")
                return {"CANCELLED"}
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Start fehlgeschlagen: {ex}")
            return {"CANCELLED"}

        # Modal warten (Timeout schützt vor ewigem Hängen)
        self._deadline = monotonic() + TIMEOUT_SEC
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event) -> Set[str]:
        if event.type == 'ESC':
            return self._finish(context, cancelled=True, msg="Abgebrochen (ESC)")

        if event.type == 'TIMER':
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
    print("[Coordinator] registered (forces helper registration)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")

# SPDX-License-Identifier: GPL-2.0-or-later
"""
Operator/tracking_coordinator.py – **modal wartend** (funktionaler Helper)

- Startet die **Funktions**-Variante `track_to_scene_end_fn(..., use_invoke=True)`.
- **Wartet modal** auf das WM‑Token, das der Helper **erst nach finalem
  Playhead‑Reset & Viewer‑Redraw** setzt.
- Meldet danach erst "Finish" (inkl. Info‑Log start → tracked_until).
"""
from __future__ import annotations

from time import time_ns, monotonic
from typing import Optional, Set

import bpy

# Funktions‑Helper + Redraw aus dem Helper‑Modul
from ..Helper.tracking_helper import track_to_scene_end_fn, _redraw_clip_editors  # type: ignore

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

TIMEOUT_SEC = 60.0


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (wait until viewer reset)"
    bl_description = (
        "Startet track_to_scene_end_fn (Forward, Sequence, INVOKE) und wartet auf das Helper-Feedback,"
        " nachdem der Viewer aktualisiert wurde."
    )
    bl_options = {"REGISTER"}

    _token: Optional[str] = None
    _timer: Optional[object] = None
    _deadline: Optional[float] = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        wm = context.window_manager

        # 1) Token vorbereiten & Slot leeren
        self._token = str(time_ns())
        try:
            wm["bw_tracking_done_token"] = ""
        except Exception:
            pass

        # 2) Helper starten (funktional, INVOKE, setzt Token **später** im Timer)
        try:
            track_to_scene_end_fn(context, coord_token=self._token, use_invoke=True)
        except Exception as ex:
            self.report({'ERROR'}, f"Helper-Fehler: {ex}")
            return {"CANCELLED"}

        # 3) Modal warten bis Token gesetzt (nach finalem Viewer-Reset)
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
                # Letzter Sicherheitsschub: Viewer redraw
                try:
                    _redraw_clip_editors(context)
                except Exception:
                    pass
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
        self._deadline = None
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
    print("[Coordinator] registered (modal wait for viewer reset)")


def unregister():
    for c in reversed(_classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    print("[Coordinator] unregistered")

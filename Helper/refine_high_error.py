# SPDX-License-Identifier: MIT
"""Refine High Error (modal).

Dieses Modul stellt einen Modal-Operator bereit, der explizit übergebene
Frame-Listen nacheinander abarbeitet. Die Kommunikation erfolgt über
Scene-Keys, analog zu den bestehenden Bidi- und Solve-Operatoren.

Scene-Keys
==========
``refine_active``: bool
    Wird beim Start auf ``True`` gesetzt und am Ende wieder ``False``.

``refine_result``: str
    Einer von ``{"FINISHED", "CANCELLED", "ERROR"}``.

``refine_error_msg``: str (optional)
    Fehlertext für Logs/Popups, wenn ``refine_result == "ERROR"``.

Payload-Keys
============
``refine_frames_json``: str
    JSON-Liste der konkreten Frames, die verarbeitet werden.

``refine_threshold``: float
    Schwelle für ``clean_tracks`` (Default: ``scene.error_track * 10``).

Optional
--------
``refine_step_ms``: int
    Timer-Tick-Intervall in Millisekunden (Default: 10).

``refine_limit_frames``: int
    Symmetrisches Fenster um den aktuellen Frame, falls keine
    ``refine_frames_json`` gesetzt ist.

Convenience-Wrapper
===================
``run_refine_on_high_error(context, frames=None, threshold=None)``
    Bereitet die Payload vor, setzt die Scene-Flags und startet den
    Modal-Operator. Es wird **nicht** auf das Ergebnis gewartet.
"""

from __future__ import annotations

import json
from typing import List, Optional, Sequence

import bpy
from bpy.types import Context, Operator

__all__ = (
    "CLIP_OT_refine_high_error",
    "run_refine_on_high_error",
    "compute_high_error_frames",
)


# -----------------------------------------------------------------------------
# Kontext-Utilities
# -----------------------------------------------------------------------------

def _clip_override(context: Context) -> Optional[dict]:
    """Ermittelt einen Override-Dict für den CLIP_EDITOR."""
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                    }
    return None


# -----------------------------------------------------------------------------
# Frame-Selection Helpers
# -----------------------------------------------------------------------------


def _get_active_clip(context: Context):
    """Ermittelt die aktive MovieClip."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _find_marker_on_frame(track, frame: int):
    """Sucht einen Marker eines Tracks auf einem spezifischen Frame."""
    for m in track.markers:
        if int(getattr(m, "frame", 0)) == int(frame):
            return m
    return None


def _frame_error(context: Context, frame: int) -> float:
    """Schätzt den Reprojektion-Error eines Frames."""
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return 0.0

    values: List[float] = []
    for track in clip.tracking.tracks:
        try:
            marker = _find_marker_on_frame(track, frame)
            err = getattr(marker, "error", None) if marker else None
            if err is None:
                err = getattr(track, "average_error", None)
            if err is not None:
                values.append(float(err))
        except Exception:
            pass

    return (sum(values) / len(values)) if values else 0.0


def compute_high_error_frames(context: Context, threshold: float) -> List[int]:
    """Liefert Frames, deren Fehler größer als ``threshold`` ist."""
    scn = context.scene
    preset = scn.get("refine_frames_json")
    if preset:
        try:
            frames = json.loads(preset)
            return [int(f) for f in frames]
        except Exception:
            pass

    frames_all = range(scn.frame_start, scn.frame_end + 1)
    return [f for f in frames_all if _frame_error(context, f) > threshold]


# -----------------------------------------------------------------------------
# Modal Operator
# -----------------------------------------------------------------------------


class CLIP_OT_refine_high_error(Operator):
    """Refine High Error (Modal)."""

    bl_idname = "clip.refine_high_error"
    bl_label = "Refine High Error (Modal)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    _timer: Optional[bpy.types.Timer] = None
    _frames: List[int]
    _idx: int = 0
    _threshold: float = 0.0

    def invoke(self, context: Context, event):
        scn = context.scene

        # Mutex-Schutz
        if scn.get("bidi_active") or scn.get("solve_active"):
            self.report({"WARNING"}, "Busy: tracking/solve active")
            return {"CANCELLED"}

        frames_json = scn.get("refine_frames_json", "[]")
        try:
            self._frames = json.loads(frames_json) or []
        except Exception:
            self._frames = []

        if not self._frames:
            self.report({"INFO"}, "No frames to refine")
            scn["refine_result"] = "FINISHED"
            scn["refine_active"] = False
            return {"CANCELLED"}

        self._threshold = float(
            scn.get("refine_threshold", float(getattr(scn, "error_track", 0.0)) * 10.0)
        )

        wm = context.window_manager
        step_ms = int(scn.get("refine_step_ms", 10))
        self._timer = wm.event_timer_add(step_ms / 1000.0, window=context.window)
        wm.modal_handler_add(self)

        scn["refine_active"] = True
        scn["refine_result"] = ""
        scn.pop("refine_error_msg", None)
        self._idx = 0
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        if event.type == "ESC":
            return self._finish(context, "CANCELLED")
        if event.type == "TIMER":
            try:
                if self._idx >= len(self._frames):
                    return self._finish(context, "FINISHED")

                frame = self._frames[self._idx]
                context.scene.frame_set(frame)

                ovr = _clip_override(context)
                if ovr:
                    bpy.ops.clip.clean_tracks(
                        ovr,
                        "EXEC_DEFAULT",
                        frames=0,
                        error=self._threshold,
                        action="SELECT",
                    )
                else:
                    bpy.ops.clip.clean_tracks(
                        "EXEC_DEFAULT",
                        frames=0,
                        error=self._threshold,
                        action="SELECT",
                    )
                self._idx += 1
            except Exception as ex:
                context.scene["refine_error_msg"] = str(ex)
                return self._finish(context, "ERROR")
        return {"PASS_THROUGH"}

    def _finish(self, context: Context, result: str):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        scn = context.scene
        scn["refine_result"] = result
        scn["refine_active"] = False

        return {"FINISHED"} if result == "FINISHED" else {"CANCELLED"}


# -----------------------------------------------------------------------------
# Convenience Wrapper
# -----------------------------------------------------------------------------


def run_refine_on_high_error(
    context: Context,
    frames: Optional[Sequence[int]] = None,
    threshold: Optional[float] = None,
):
    """Startet den Refine-Modaloperator mit vorbereiteten Scene-Keys."""

    scn = context.scene
    if scn.get("bidi_active") or scn.get("solve_active") or scn.get("refine_active"):
        return {"status": "BUSY"}

    th = (
        float(threshold)
        if threshold is not None
        else float(getattr(scn, "error_track", 0.0)) * 10.0
    )

    if frames is None:
        frames = compute_high_error_frames(context, th)

    frames = [int(f) for f in frames]
    if not frames:
        scn["refine_result"] = "FINISHED"
        scn["refine_active"] = False
        print("[Refine] No frames above threshold; skipping.")
        return {"status": "FINISHED", "frames": []}

    scn["refine_frames_json"] = json.dumps(frames)
    scn["refine_threshold"] = th
    scn["refine_result"] = ""
    scn["refine_active"] = True
    scn.pop("refine_error_msg", None)

    ovr = _clip_override(context)
    if ovr:
        bpy.ops.clip.refine_high_error(ovr, "INVOKE_DEFAULT")
    else:
        bpy.ops.clip.refine_high_error("INVOKE_DEFAULT")

    return {"status": "STARTED", "frames": frames, "threshold": th}


# -----------------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------------


_classes = (CLIP_OT_refine_high_error,)


def register() -> None:
    from bpy.utils import register_class

    for cls in _classes:
        register_class(cls)


def unregister() -> None:
    from bpy.utils import unregister_class

    for cls in reversed(_classes):
        unregister_class(cls)


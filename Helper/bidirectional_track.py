from __future__ import annotations

import time
from typing import Optional, Tuple

import bpy
from bpy.types import Operator


# ---------------------------------------------------------------------------
# UI/Context-Utilities
# ---------------------------------------------------------------------------

def _find_clip_context() -> Tuple[Optional[bpy.types.Window],
                                  Optional[bpy.types.Area],
                                  Optional[bpy.types.Region],
                                  Optional[bpy.types.Space]]:
    wm = bpy.context.window_manager
    if not wm:
        return None, None, None, None
    for win in wm.windows:
        scr = win.screen
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'CLIP_EDITOR':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                space = area.spaces.active if hasattr(area, "spaces") else None
                if region and space:
                    return win, area, region, space
    return None, None, None, None


def _run_in_clip_context(op_callable, **kwargs):
    win, area, region, space = _find_clip_context()
    if not (win and area and region and space):
        return op_callable(**kwargs)
    override = {
        "window": win,
        "area": area,
        "region": region,
        "space_data": space,
        "scene": bpy.context.scene,
    }
    with bpy.context.temp_override(**override):
        return op_callable(**kwargs)


def _get_active_clip_fallback() -> Optional[bpy.types.MovieClip]:
    _, _, _, space = _find_clip_context()
    if space:
        clip = getattr(space, "clip", None)
        if clip:
            return clip
    try:
        for c in bpy.data.movieclips:
            return c
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Marker/Track-Utilities
# ---------------------------------------------------------------------------

def _count_total_markers(clip) -> int:
    try:
        return sum(len(t.markers) for t in clip.tracking.tracks)
    except Exception:
        return 0


def _count_tracks_with_marker_on_frame(clip, frame: int) -> int:
    cnt = 0
    try:
        for tr in clip.tracking.tracks:
            try:
                mk = tr.markers.find_frame(frame, exact=True)
            except TypeError:
                mk = tr.markers.find_frame(frame)
            if mk and not getattr(mk, "mute", False):
                cnt += 1
    except Exception:
        pass
    return cnt


def _deselect_all_tracks(clip) -> None:
    try:
        for t in clip.tracking.tracks:
            t.select = False
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class CLIP_OT_bidirectional_track(Operator):
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track"
    bl_description = "Trackt Marker vorwärts und rückwärts (sichtbar im UI) und signalisiert Fertig an Orchestrator"

    _timer = None
    _step = 0
    _start_frame = 0

    _prev_marker_count = -1
    _prev_frame = -1
    _stable_count = 0

    _t0 = 0.0
    _tick = 0
    _t_last_action = 0.0

    # ---------------------------------------------------------------------

    def execute(self, context):
        context.scene["bidi_active"] = True
        context.scene["bidi_result"] = ""

        self._step = 0
        self._stable_count = 0
        self._prev_marker_count = -1
        self._prev_frame = -1
        self._start_frame = context.scene.frame_current

        self._t0 = time.perf_counter()
        self._t_last_action = self._t0
        self._tick = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    # ---------------------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1
            return self.run_tracking_step(context)
        return {'PASS_THROUGH'}

    # ---------------------------------------------------------------------

    def run_tracking_step(self, context):
        clip = _get_active_clip_fallback()
        if clip is None:
            self.report({'ERROR'}, "Kein aktiver Clip im Tracking-Editor gefunden.")
            return self._finish(context, result="FAILED")

        if self._step == 0:
            try:
                bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=False, sequence=True)
            except Exception:
                return self._finish(context, result="FAILED")
            self._t_last_action = time.perf_counter()
            self._step = 1
            return {'PASS_THROUGH'}

        elif self._step == 1:
            context.scene.frame_current = self._start_frame
            self._step = 2
            return {'PASS_THROUGH'}

        elif self._step == 2:
            self._step = 3
            return {'PASS_THROUGH'}

        elif self._step == 3:
            try:
                bpy.ops.clip.track_markers('INVOKE_DEFAULT', backwards=True, sequence=True)
            except Exception:
                return self._finish(context, result="FAILED")
            self._t_last_action = time.perf_counter()
            self._step = 4
            return {'PASS_THROUGH'}

        elif self._step == 4:
            return self._finish(context, result="OK")

        return {'PASS_THROUGH'}

    # ---------------------------------------------------------------------

    def _finish(self, context, result: str):
        wm = context.window_manager
        if self._timer:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

        context.scene["bidi_active"] = False
        context.scene["bidi_result"] = result
        return {'FINISHED'}

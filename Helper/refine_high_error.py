from __future__ import annotations
import bpy
import time
from math import isfinite
from typing import List, Optional
from bpy.types import Operator, Context


# ------------------------- Kontext & Mapping ---------------------------------

def _find_clip_area_ctx(context: Context) -> Optional[dict]:
    win = context.window
    scr = win.screen if win else None
    if not win or not scr:
        return None
    area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        return None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    space = area.spaces.active if area.spaces and area.spaces.active.type == 'CLIP_EDITOR' else None
    ctx = dict(window=win, screen=scr, area=area, region=region)
    if space:
        ctx["space_data"] = space
        if getattr(space, "clip", None):
            ctx["edit_movieclip"] = space.clip
    return ctx


def _scene_to_clip_frame(context: Context, clip: bpy.types.MovieClip, scene_frame: int) -> int:
    scn = context.scene
    scene_start = int(getattr(scn, "frame_start", 1))
    clip_start = int(getattr(clip, "frame_start", 1))
    scn_fps = float(getattr(getattr(scn, "render", None), "fps", 0) or 0.0)
    clip_fps = float(getattr(clip, "fps", 0) or 0.0)
    scale = (clip_fps / scn_fps) if (scn_fps > 0.0 and clip_fps > 0.0) else 1.0
    rel = round((scene_frame - scene_start) * scale)
    f = int(clip_start + rel)
    dur = int(getattr(clip, "frame_duration", 0) or 0)
    if dur > 0:
        fmin, fmax = clip_start, clip_start + dur - 1
        f = max(fmin, min(f, fmax))
    return f


def _force_visible_playhead(context: Context, ovr: dict, clip: bpy.types.MovieClip,
                            scene_frame: int, *, sleep_s: float = 0.04) -> None:
    # 1) Szene-Frame
    context.scene.frame_set(int(scene_frame))
    # 2) Clip-User-Frame synchronisieren
    try:
        cf = _scene_to_clip_frame(context, clip, int(scene_frame))
        space = ovr.get("space_data", None)
        if space and getattr(space, "clip_user", None):
            space.clip_user.frame_current = int(cf)
    except Exception:
        pass
    # 3) View-Layer & Redraw
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    try:
        area = ovr.get("area", None)
        if area:
            area.tag_redraw()
        with context.temp_override(**ovr):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass
    # 4) kleine Atempause für die UI
    if sleep_s > 0.0:
        try:
            time.sleep(float(sleep_s))
        except Exception:
            pass


# ------------------------- Marker/Track Helpers ------------------------------

def _marker_on_clip_frame(track, frame_clip: int):
    try:
        return track.markers.find_frame(frame_clip, exact=False)
    except Exception:
        return None


def _iter_tracks_with_marker_at_clip_frame(tracks, frame_clip: int):
    for tr in tracks:
        if hasattr(tr, "enabled") and not bool(getattr(tr, "enabled")):
            continue
        mk = _marker_on_clip_frame(tr, frame_clip)
        if mk is None:
            continue
        if hasattr(mk, "mute") and bool(getattr(mk, "mute")):
            continue
        yield tr


def _marker_error_on_clip_frame(track, frame_clip: int):
    try:
        mk = _marker_on_clip_frame(track, frame_clip)
        if mk is not None and hasattr(mk, "error"):
            v = float(mk.error)
            if isfinite(v):
                return v
    except Exception:
        pass
    try:
        v = float(getattr(track, "average_error"))
        return v if isfinite(v) else None
    except Exception:
        return None


def _set_selection_for_tracks_on_clip_frame(tob, frame_clip: int, tracks_subset):
    # clear
    for t in tob.tracks:
        try:
            t.select = False
            for m in t.markers:
                m.select = False
        except Exception:
            pass
    # set
    for t in tracks_subset:
        try:
            mk = _marker_on_clip_frame(t, frame_clip)
            if mk is None:
                continue
            t.select = True
            mk.select = True
        except Exception:
            pass


# ------------------------- Modal Operator ------------------------------------

class CLIP_OT_refine_high_error_modal(Operator):
    """Refine High Error (minimal modal, UI-responsiv, ohne Extras)"""
    bl_idname = "clip.refine_high_error_modal"
    bl_label = "Refine High Error (Modal)"
    bl_options = {"REGISTER", "INTERNAL"}

    # Parameter
    error_track: bpy.props.FloatProperty(default=2.0)  # type: ignore
    only_selected_tracks: bpy.props.BoolProperty(default=False)  # type: ignore
    wait_seconds: bpy.props.FloatProperty(default=0.05, min=0.0, soft_max=0.5)  # type: ignore
    ui_sleep_s: bpy.props.FloatProperty(default=0.04, min=0.0, soft_max=0.2)  # type: ignore
    max_refine_calls: bpy.props.IntProperty(default=20, min=1)  # type: ignore
    tracking_object_name: bpy.props.StringProperty(default="")  # type: ignore

    # intern
    _timer = None
    _ovr: Optional[dict] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _tob = None
    _tracks: List = []
    _frame_scene: int = 0
    _frame_end: int = 0
    _ops_left: int = 0

    def invoke(self, context: Context, event):
        # Context/Clip ermitteln
        self._ovr = _find_clip_area_ctx(context)
        if not self._ovr:
            self.report({"ERROR"}, "Kein Movie Clip Editor im aktuellen Screen")
            return {"CANCELLED"}
        self._clip = self._ovr.get("edit_movieclip") or getattr(self._ovr.get("space_data"), "clip", None)
        if not self._clip:
            self.report({"ERROR"}, "Kein Movie Clip aktiv")
            return {"CANCELLED"}

        tracking = self._clip.tracking
        recon = getattr(tracking, "reconstruction", None)
        if not recon or not getattr(recon, "is_valid", False):
            self.report({"ERROR"}, "Rekonstruktion ist nicht gültig. Erst solve durchführen.")
            return {"CANCELLED"}

        self._tob = (tracking.objects.get(self.tracking_object_name)
                     if self.tracking_object_name else tracking.objects.active)
        if self._tob is None:
            self.report({"ERROR"}, "Kein Tracking-Objekt aktiv")
            return {"CANCELLED"}

        self._tracks = list(self._tob.tracks)
        if self.only_selected_tracks:
            self._tracks = [t for t in self._tracks if getattr(t, "select", False)]
        if not self._tracks:
            self.report({"WARNING"}, "Keine passenden Tracks gefunden")
            return {"CANCELLED"}

        scn = context.scene
        self._frame_scene = scn.frame_start
        self._frame_end = scn.frame_end
        self._ops_left = int(self.max_refine_calls)

        # Flag setzen: läuft
        scn["refine_active"] = True

        # Timer
        step = max(0.01, min(0.2, float(self.wait_seconds) * 0.5))
        self._timer = context.window_manager.event_timer_add(step, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        try:
            if self._ops_left <= 0 or self._frame_scene > self._frame_end:
                return self._finish(context, cancelled=False)

            # Frame vorbereiten
            f_scene = self._frame_scene
            f_clip = _scene_to_clip_frame(context, self._clip, f_scene)
            active_tracks = list(_iter_tracks_with_marker_at_clip_frame(self._tracks, f_clip))
            mea = len(active_tracks)

            if mea > 0:
                # FE berechnen
                me = 0.0
                for t in active_tracks:
                    v = _marker_error_on_clip_frame(t, f_clip)
                    if v is not None:
                        me += v
                fe = me / float(mea) if mea else 0.0

                if fe > (float(self.error_track) * 2.0):
                    # Playhead zeigen
                    _force_visible_playhead(context, self._ovr, self._clip, f_scene, sleep_s=float(self.ui_sleep_s))

                    # Auswahl setzen (alle Marker im Frame)
                    _set_selection_for_tracks_on_clip_frame(self._tob, f_clip, active_tracks)

                    # refine vorwärts
                    if self._ops_left > 0:
                        with context.temp_override(**self._ovr):
                            bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=False)
                        self._ops_left -= 1
                        with context.temp_override(**self._ovr):
                            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

                    # refine rückwärts (wenn Budget)
                    if self._ops_left > 0:
                        if float(self.wait_seconds) > 0.0:
                            time.sleep(min(0.2, float(self.wait_seconds)))
                        with context.temp_override(**self._ovr):
                            bpy.ops.clip.refine_markers('EXEC_DEFAULT', backwards=True)
                        self._ops_left -= 1
                        with context.temp_override(**self._ovr):
                            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            # Nächster Frame
            self._frame_scene += 1
            return {"RUNNING_MODAL"}

        except Exception as ex:
            print(f"[RefineModal] Error: {ex!r}")
            return self._finish(context, cancelled=True)

    def _finish(self, context: Context, *, cancelled: bool):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        try:
            context.scene["refine_active"] = False
        except Exception:
            pass
        print(f"[RefineModal] DONE ({'CANCELLED' if cancelled else 'FINISHED'})")
        return {"CANCELLED" if cancelled else "FINISHED"}


# ------------------------- Public API ----------------------------------------

def start_refine_modal(
    context: Context,
    *,
    error_track: float,
    only_selected_tracks: bool = False,
    wait_seconds: float = 0.05,
    ui_sleep_s: float = 0.04,
    max_refine_calls: int = 20,
    tracking_object_name: str | None = None,
) -> dict:
    """
    Startet den modal Refine-Operator. Rückgabe: {'status': 'STARTED'|'BUSY'|'FAILED'}.
    Coordinator kann über scene['refine_active'] warten.
    """
    scn = context.scene
    if scn.get("refine_active"):
        return {"status": "BUSY"}

    ovr = _find_clip_area_ctx(context)
    if not ovr:
        return {"status": "FAILED", "reason": "no_clip_editor"}

    kwargs = dict(
        error_track=float(error_track),
        only_selected_tracks=bool(only_selected_tracks),
        wait_seconds=float(wait_seconds),
        ui_sleep_s=float(ui_sleep_s),
        max_refine_calls=int(max_refine_calls),
        tracking_object_name=str(tracking_object_name or ""),
    )
    with context.temp_override(**ovr):
        bpy.ops.clip.refine_high_error_modal('INVOKE_DEFAULT', **kwargs)
    return {"status": "STARTED", **kwargs}


# Register
_CLASSES = (CLIP_OT_refine_high_error_modal,)

def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)

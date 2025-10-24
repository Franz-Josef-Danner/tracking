# Operator/master_operator.py
import bpy
from typing import Any, Optional, Set, Dict, Callable, ContextManager
from contextlib import contextmanager

# Helper-Importe
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.filter_tracks import filter_problematic_tracks
from ..Helper.thresh_map import (
    should_use_cached_thresholds,
    save_after_autocalibrate,
)

# ---------------------------------------------------------------------------
# Context & Selection Utilities
# ---------------------------------------------------------------------------

def _find_clip_editor_area_for_clip(clip: Optional[bpy.types.MovieClip]):
    """Sucht eine CLIP_EDITOR-Area (mit passendem Space/Region) für Context Override."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
            if not region_window:
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                if getattr(space, "clip", None) == clip or space.clip is None:
                    return window, area, region_window, space
    return None, None, None, None


def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    sd = getattr(context, "space_data", None)
    return getattr(sd, "clip", None) if sd else None


def _coerce_frame(result: Any) -> Optional[int]:
    """Erlaubt flexible Rückgaben von find_first_weak_frame."""
    if result is None:
        return None
    if isinstance(result, int):
        return int(result)
    if isinstance(result, (tuple, list)) and result:
        first = result[0]
        return int(first) if isinstance(first, (int, float)) else None
    return None


def _snapshot_selected_track_names(clip: Optional[bpy.types.MovieClip]) -> Set[str]:
    names: Set[str] = set()
    if not clip:
        return names
    tracking = clip.tracking
    for track in tracking.tracks:
        if getattr(track, "select", False):
            names.add(track.name)
    return names


def _restore_selected_tracks_by_names(clip: Optional[bpy.types.MovieClip], names: Set[str]) -> None:
    if not clip or not names:
        return
    tracking = clip.tracking
    for track in tracking.tracks:
        track.select = False
    for track in tracking.tracks:
        if track.name in names:
            track.select = True


def _set_frame_in_scene_and_clip(context: bpy.types.Context, frame: int) -> None:
    """Setzt Playhead global und im Clip-Editor (falls möglich)."""
    context.scene.frame_current = int(frame)
    clip = _get_active_clip(context)
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        try:
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
                bpy.ops.clip.change_frame(frame=int(frame))
        except Exception:
            try:
                region.tag_redraw()
            except Exception:
                pass


@contextmanager
def _clip_context(context: bpy.types.Context, clip: Optional[bpy.types.MovieClip]) -> ContextManager[None]:
    """
    Liefert einen sicheren Override-Kontext für CLIP_EDITOR-Operatoren via temp_override.
    Nur erlaubte Keys; kein 'screen' (wird intern aus window abgeleitet).
    """
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
            yield
    else:
        yield


def _call_op_in_clip(op_callable, context: bpy.types.Context, clip: Optional[bpy.types.MovieClip], **kwargs) -> bool:
    """
    Führt einen Blender-Operator im CLIP_EDITOR-Kontext aus (temp_override).
    Rückgabe: True bei {'FINISHED'}, sonst False. Keine Logausgabe.
    """
    try:
        with _clip_context(context, clip):
            result = op_callable(**kwargs)
        return bool(hasattr(result, "__contains__") and "FINISHED" in result)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Master Operator
# ---------------------------------------------------------------------------

# Operator/master_operator.py (ersetzt execute() & ergänzt modal-Handling)

class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — Master Operator (Modal)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    _timer = None
    _phase = 0
    _iteration = 0
    _max_iter = 50

    def execute(self, context):
        scene = context.scene
        clip = _get_active_clip(context)
        if not clip:
            self.report({"ERROR"}, "Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        # Flags setzen
        scene["kaiserlich_tracking_in_progress"] = True
        scene["kaiserlich_tracking_forward_done"] = False
        scene["kaiserlich_tracking_backward_done"] = False
        scene["kaiserlich_autocalibrate_done"] = False

        # Tracking starten
        print("[Kaiserlich Tracker][Master] Initiiere Tracking-Vorgang ...")
        try:
            bpy.ops.kaiserlich_tracker.track_cycle_backwards('INVOKE_DEFAULT')
            bpy.ops.kaiserlich_tracker.track_cycle('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'ERROR'}, f"Tracking konnte nicht gestartet werden: {e}")
            return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.3, window=context.window)
        wm.modal_handler_add(self)
        self._phase = 1
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'ESC':
            self._finish(context, cancelled=True)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # ----------------------------
        # Phase 1: Tracking abwarten
        # ----------------------------
        if self._phase == 1:
            f_done = scene.get("kaiserlich_tracking_forward_done", False)
            b_done = scene.get("kaiserlich_tracking_backward_done", False)
            if f_done and b_done:
                print("[Kaiserlich Tracker][Master] ✓ Tracking abgeschlossen → starte AutoCalibrate ...")
                self._phase = 2
                try:
                    bpy.ops.kaiserlich_tracker.auto_calibrate_modal('INVOKE_DEFAULT')
                except Exception as e:
                    print(f"[Master] AutoCalibrate Modal Fehler: {e}")
                    self._finish(context, cancelled=True)
                    return {'CANCELLED'}

        # ----------------------------
        # Phase 2: Warte auf AutoCalibrate
        # ----------------------------
        elif self._phase == 2:
            ac_done = scene.get("kaiserlich_autocalibrate_done", False)
            if ac_done:
                print("[Kaiserlich Tracker][Master] AutoCalibrate abgeschlossen → starte DetectAdapt ...")
                self._phase = 3
                try:
                    bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
                except Exception as e:
                    print(f"[Master] DetectAdapt Fehler: {e}")

        # ----------------------------
        # Phase 3: Filter + Cleanup
        # ----------------------------
        elif self._phase == 3:
            print("[Kaiserlich Tracker][Master] Cleanup + Filter ...")
            try:
                filter_problematic_tracks(context, threshold=10.0)
            except Exception:
                pass
            self._finish(context)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        if cancelled:
            print("[Kaiserlich Tracker][Master] Abgebrochen.")
        else:
            print("[Kaiserlich Tracker][Master] Modal beendet ✓")
        scene = context.scene
        scene["kaiserlich_tracking_in_progress"] = False

# --- Registrierung ----------------------------------------------------------

classes = (
    KAISERLICHTRACKER_OT_master_operator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

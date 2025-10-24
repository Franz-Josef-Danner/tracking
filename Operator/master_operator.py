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
    """Iterative Low-Marker-Pipeline (modal):
    low_marker_frame -> (auto_calibrate?) -> detect_adapt -> track_backwards -> track_forwards,
    bis kein Low-Marker-Frame mehr existiert.
    """
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — Master Operator"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    set_playhead: bpy.props.BoolProperty(
        name="Playhead setzen",
        description="Playhead im Clip Editor auf den gefundenen Frame setzen",
        default=True,
    )

    store_scene_key: bpy.props.StringProperty(
        name="Scene Key",
        description="Szenen-Property zum Ablegen des gefundenen Frames",
        default="kaiserlich_low_marker_frame",
    )

    max_iterations: bpy.props.IntProperty(
        name="Max Iterationen",
        description="Safety-Stop gegen Endlosschleifen",
        default=100,
        min=1,
        soft_min=1,
    )

    _timer = None
    _phase = 0
    _iteration = 0
    _saved_selection = None
    _active_clip = None
    _current_frame = None

    # -------------------------------------------------------------
    # Start / Init
    # -------------------------------------------------------------
    def execute(self, context):
        scene = context.scene
        clip = _get_active_clip(context)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip im Movie Clip Editor gefunden.")
            return {'CANCELLED'}

        self._active_clip = clip
        self._saved_selection = _snapshot_selected_track_names(clip)
        self._iteration = 0
        self._phase = 0
        scene["kaiserlich_master_running"] = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.3, window=context.window)
        wm.modal_handler_add(self)
        print("[Kaiserlich Tracker][Master] Starte modale Iterations-Pipeline ...")
        return {'RUNNING_MODAL'}

    # -------------------------------------------------------------
    # Modal Loop
    # -------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            self._finish(context, cancelled=True)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene
        clip = self._active_clip

        # Safety
        if self._iteration >= self.max_iterations:
            self.report({'ERROR'}, f"Abbruch durch Safety-Stop nach {self.max_iterations} Iterationen.")
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        # -------------------------------
        # Phase 0 – neuen Low-Marker suchen
        # -------------------------------
        if self._phase == 0:
            self._iteration += 1
            print(f"[Master] Iteration {self._iteration} – Suche schwächsten Frame ...")
            try:
                res = find_first_weak_frame(context)
                frame = _coerce_frame(res)
                if frame is None:
                    print("[Master] Kein Low-Marker-Frame mehr gefunden → Pipeline beendet.")
                    self._finish(context)
                    return {'FINISHED'}
                self._current_frame = frame
                scene[self.store_scene_key] = int(frame)
                if self.set_playhead:
                    _set_frame_in_scene_and_clip(context, frame)
            except Exception as e:
                self.report({'ERROR'}, f"find_first_weak_frame() Fehler: {e}")
                self._finish(context, cancelled=True)
                return {'CANCELLED'}

            # prüfen ob AutoCalibrate übersprungen werden kann
            try:
                self._skip_auto = should_use_cached_thresholds(context, frame)
            except Exception:
                self._skip_auto = False

            # → nächste Phase
            self._phase = 1
            return {'RUNNING_MODAL'}

        # -------------------------------
        # Phase 1 – AutoCalibrate (falls nötig)
        # -------------------------------
        if self._phase == 1:
            if not getattr(self, "_auto_started", False):
                if not self._skip_auto:
                    print("[Master] Starte Auto-Calibrate (modal) ...")
                    try:
                        bpy.ops.kaiserlich_tracker.auto_calibrate_modal('INVOKE_DEFAULT')
                    except Exception as e:
                        self.report({'ERROR'}, f"Auto-Calibrate konnte nicht gestartet werden: {e}")
                        self._finish(context, cancelled=True)
                        return {'CANCELLED'}
                else:
                    print("[Master] Überspringe Auto-Calibrate (Cache vorhanden).")
                    self._phase = 2
                    return {'RUNNING_MODAL'}
                self._auto_started = True
                return {'RUNNING_MODAL'}
            else:
                ac_done = scene.get("kaiserlich_autocalibrate_done", False)
                if ac_done or self._skip_auto:
                    try:
                        if not self._skip_auto:
                            save_after_autocalibrate(context, self._current_frame, bake_neighbors=True)
                    except Exception:
                        pass
                    print("[Master] Auto-Calibrate abgeschlossen → starte DetectAdapt ...")
                    self._phase = 2
                    return {'RUNNING_MODAL'}

        # -------------------------------
        # Phase 2 – Detect Adapt
        # -------------------------------
        if self._phase == 2:
            print("[Master] Detect Adapt ...")
            _call_op_in_clip(bpy.ops.kaiserlich_tracker.detect_adapt, context, clip)
            self._phase = 3
            return {'RUNNING_MODAL'}

        # -------------------------------
        # Phase 3 – Track Backwards
        # -------------------------------
        if self._phase == 3:
            print("[Master] Track Backwards ...")
            bpy.ops.kaiserlich_tracker.track_cycle_backwards('INVOKE_DEFAULT')
            self._phase = 4
            return {'RUNNING_MODAL'}

        # -------------------------------
        # Phase 4 – Track Forwards
        # -------------------------------
        if self._phase == 4:
            print("[Master] Track Forwards ...")
            bpy.ops.kaiserlich_tracker.track_cycle('INVOKE_DEFAULT')
            self._phase = 5
            return {'RUNNING_MODAL'}

        # -------------------------------
        # Phase 5 – Cleanup + Nächste Iteration
        # -------------------------------
        if self._phase == 5:
            print("[Master] Filter / Cleanup ...")
            try:
                filter_problematic_tracks(context, threshold=10.0)
            except Exception:
                pass
            _restore_selected_tracks_by_names(clip, self._saved_selection)
            self._phase = 0  # -> nächste Iteration
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # -------------------------------------------------------------
    # Abschluss
    # -------------------------------------------------------------
    def _finish(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        scene = context.scene
        _restore_selected_tracks_by_names(self._active_clip, self._saved_selection)
        scene["kaiserlich_master_running"] = False
        if cancelled:
            print("[Kaiserlich Tracker][Master] Modal abgebrochen.")
        else:
            print("[Kaiserlich Tracker][Master] ✓ vollständig abgeschlossen.")

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

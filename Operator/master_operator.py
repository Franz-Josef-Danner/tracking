import bpy
from typing import Any, Optional, Set, Dict, Callable, ContextManager
from contextlib import contextmanager

# Helper-Import
from ..Helper.low_marker_frame import find_first_weak_frame


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
        # Fallback: kein Override möglich, Operatoren laufen im aktuellen Kontext
        yield


def _op_id(op) -> str:
    """Robustes Operator-Label fürs Logging."""
    try:
        return op.idname()
    except Exception:
        return repr(op)


def _call_op_in_clip(op_callable, context: bpy.types.Context, clip: Optional[bpy.types.MovieClip], **kwargs) -> bool:
    """
    Führt einen Blender-Operator im CLIP_EDITOR-Kontext aus (temp_override).
    Rückgabe: True bei {'FINISHED'}, sonst False. Crash-sicher geloggt.
    """
    try:
        with _clip_context(context, clip):
            result = op_callable(**kwargs)
        if hasattr(result, "__contains__") and "FINISHED" in result:
            return True
        return False
    except Exception as e:
        print(f"[Kaiserlich Tracker][Master] Operator-Call fehlgeschlagen: {_op_id(op_callable)} -> {e}")
        return False


# ---------------------------------------------------------------------------
# Master Operator
# ---------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):
    """Iterative Low-Marker-Pipeline: low_marker_frame -> auto_calibrate -> detect_adapt -> track_backwards -> track_forwards, bis kein Low-Marker-Frame mehr existiert."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — Master Operator"
    bl_options = {"REGISTER", "UNDO"}

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

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = _get_active_clip(context)

        # Selektion sichern
        saved_selection = _snapshot_selected_track_names(clip)

        iterations = 0
        total_hits = 0

        while iterations < self.max_iterations:
            iterations += 1

            # 1) Low-Marker-Frame bestimmen
            try:
                res = find_first_weak_frame(context)
            except Exception as e:
                self.report({"ERROR"}, f"find_first_weak_frame() Fehler: {e}")
                break

            frame = _coerce_frame(res)
            if frame is None:
                self.report({"INFO"}, f"Kein Low-Marker-Frame mehr gefunden. Iterationen: {iterations-1}, Hits: {total_hits}")
                print(f"[Kaiserlich Tracker][Master] Completed. Iterations={iterations-1}, Hits={total_hits}")
                break

            total_hits += 1

            # Persistenz
            try:
                scene[self.store_scene_key] = int(frame)
            except Exception:
                pass

            # Playhead setzen
            if self.set_playhead:
                _set_frame_in_scene_and_clip(context, frame)

            print(f"[Kaiserlich Tracker][Master] Iteration={iterations} -> LowMarkerFrame={frame}")

            # 2) Auto-Calibrate
            ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.auto_calibrate, context, clip)
            if not ok:
                self.report({"WARNING"}, "auto_calibrate wurde nicht erfolgreich ausgeführt.")
            else:
                print("[Kaiserlich Tracker][Master] auto_calibrate: OK")

            # 3) Detect Adapt
            ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.detect_adapt, context, clip)
            if not ok:
                self.report({"WARNING"}, "detect_adapt wurde nicht erfolgreich ausgeführt.")
            else:
                print("[Kaiserlich Tracker][Master] detect_adapt: OK")

            # 4) Track Cycle Backwards
            ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.track_cycle_backwards, context, clip)
            if not ok:
                self.report({"WARNING"}, "track_cycle_backwards wurde nicht erfolgreich ausgeführt.")
            else:
                print("[Kaiserlich Tracker][Master] track_cycle_backwards: OK")

            # 5) Track Cycle Forwards
            ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.track_cycle, context, clip)
            if not ok:
                self.report({"WARNING"}, "track_cycle (vorwärts) wurde nicht erfolgreich ausgeführt.")
            else:
                print("[Kaiserlich Tracker][Master] track_cycle (forward): OK")

            # Optional: Selektion nach jedem Loop wiederherstellen
            _restore_selected_tracks_by_names(clip, saved_selection)

        # Final: Selektion sicherstellen
        _restore_selected_tracks_by_names(clip, saved_selection)

        if iterations >= self.max_iterations:
            self.report({"WARNING"}, f"Abbruch durch Safety-Stop nach {self.max_iterations} Iterationen.")
            print(f"[Kaiserlich Tracker][Master] Safety stop reached at {self.max_iterations} iterations.")

        return {"FINISHED"}


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

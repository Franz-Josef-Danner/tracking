# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable, List, Set, Optional

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import get_start_frame, reset_to_frame

SCENE_TOTAL_TRACK_LEN_KEY = "kaiserlich_track_length_total"

# ---- Utility ---------------------------------------------------------------

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    for p in props:
        if hasattr(scene, p):
            try:
                setattr(scene, p, 1.0)
            except Exception:
                pass  # fail-soft


def _call_get_start_frame(context=None):
    try:
        return get_start_frame(context) if context is not None else get_start_frame()
    except TypeError:
        return get_start_frame()


def _call_reset_to_frame(frame, context=None):
    try:
        return reset_to_frame(context, frame) if context is not None else reset_to_frame(frame)
    except TypeError:
        return reset_to_frame(frame)


def _get_active_clip(context: Optional[bpy.types.Context]) -> Optional[bpy.types.MovieClip]:
    try:
        if context and getattr(context, "space_data", None):
            clip = getattr(context.space_data, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _list_track_names_from_clip(clip: Optional[bpy.types.MovieClip]):
    if not clip:
        return []
    try:
        return [t.name for t in clip.tracking.tracks]
    except Exception:
        return []


def _get_current_track_names(context: Optional[bpy.types.Context]) -> Set[str]:
    clip = _get_active_clip(context)
    return set(_list_track_names_from_clip(clip))


def auto_calibrate_pipeline(context=None, tracks_to_delete=None):
    """
    Reihenfolge:
      0) set_all_thresholds_to_one
      1) snapshot_active_markers
      2) bpy.ops.kaiserlich_tracker.detect_adapt
      2.5) get_start_frame
      3) bpy.ops.kaiserlich_tracker.track_cycle
      4) delete_tracks_by_names (explizit/optional)
      5) reset_to_frame(start)
      6) delete newly created tracks (Delta)
      7) FINAL: get_total_track_length und in Scene speichern
    Returns:
      dict: {"total_track_length": float, "deleted_explicit": [str], "deleted_new": [str], "start_frame": int|None}
    """
    start_frame = None
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []
    final_total_len: float = 0.0

    # Vorher-Stand der Tracks für Delta-Ermittlung
    pre_names: Set[str] = _get_current_track_names(context)

    try:
        # 0) Thresholds
        if context is not None:
            try:
                set_all_thresholds_to_one(context)
            except Exception:
                pass

        # 1) Snapshot
        try:
            (snapshot_active_markers(context) if context is not None else snapshot_active_markers())
        except TypeError:
            snapshot_active_markers()

        # 2) Detect-Adapt
        result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Detect-Adapt wurde abgebrochen.")

        # 2.5) Start-Frame
        start_frame = _call_get_start_frame(context)

        # 3) Track Cycle
        result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Tracking Cycle wurde abgebrochen.")

        # 4) Optional: explizit angegebene Tracks löschen
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                try:
                    (delete_tracks_by_names(context, names) if context is not None else delete_tracks_by_names(names))
                except TypeError:
                    delete_tracks_by_names(names)
                deleted_explicit = names

    finally:
        # 5) Playhead zurücksetzen (best effort)
        if start_frame is not None:
            try:
                _call_reset_to_frame(start_frame, context)
            except Exception:
                pass

        # 6) NEU: neu erzeugte Tracks löschen (Delta)
        try:
            post_names: Set[str] = _get_current_track_names(context)
            new_names = sorted(list(post_names - pre_names))
            if new_names:
                try:
                    (delete_tracks_by_names(context, new_names) if context is not None else delete_tracks_by_names(new_names))
                except TypeError:
                    delete_tracks_by_names(new_names)
                deleted_new = new_names
        except Exception:
            pass

        # 7) FINAL: Gesamtlänge nach allen Löschungen bestimmen UND in Scene speichern
        try:
            if context is not None:
                try:
                    final_total_len = float(get_total_track_length(context))
                except TypeError:
                    final_total_len = float(get_total_track_length())
            else:
                final_total_len = float(get_total_track_length())
        except Exception:
            final_total_len = 0.0  # fail-soft

        try:
            scene = context.scene if context is not None else bpy.context.scene
            scene[SCENE_TOTAL_TRACK_LEN_KEY] = final_total_len
        except Exception:
            # Kein Hard-Fail, falls Scene nicht schreibbar ist
            pass

    return {
        "total_track_length": final_total_len,   # FINALER Wert (nach Cleanup)
        "deleted_explicit": deleted_explicit,
        "deleted_new": deleted_new,
        "start_frame": start_frame,
    }


# ---- Operator --------------------------------------------------------------

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto-calibrate: initialisiert alle Ziel-Parameter auf 1 und führt danach Detect-Adapt und Tracking aus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "KAISERLICHTRACKER — Auto Calibrate"
    bl_options = {"REGISTER", "UNDO"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks, getrennt durch Kommas"
    )

    def execute(self, context):
        try:
            # UI-Feedback
            set_all_thresholds_to_one(context)
            self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")

            names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
            result = auto_calibrate_pipeline(context=context, tracks_to_delete=names)

            final_len = result.get('total_track_length', 0.0)
            self.report({'INFO'}, f"Auto-Calibrate finalisiert. Track-Länge gesamt (persistiert): {final_len}")
            if result.get("deleted_explicit"):
                self.report({'INFO'}, f"Explizit gelöschte Tracks: {', '.join(result['deleted_explicit'])}")
            if result.get("deleted_new"):
                self.report({'INFO'}, f"Neu erzeugte Tracks entfernt: {', '.join(result['deleted_new'])}")
            if result.get("start_frame") is not None:
                self.report({'INFO'}, f"Playhead zurückgesetzt auf Frame {result['start_frame']}")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

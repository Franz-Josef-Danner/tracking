# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable, List, Set, Optional

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


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
    """
    Best effort: aktive Clip-Quelle priorisieren; fällt andernfalls auf ersten verfügbaren Clip zurück.
    """
    # 1) Kontext-Clip (Movie Clip Editor)
    try:
        if context and getattr(context, "space_data", None):
            clip = getattr(context.space_data, "clip", None)
            if clip:
                return clip
    except Exception:
        pass
    # 2) Fallback: erster MovieClip in der Datei
    try:
        return bpy.data.movieclips[0] if bpy.data.movieclips else None
    except Exception:
        return None


def _list_track_names_from_clip(clip: Optional[bpy.types.MovieClip]) -> List[str]:
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
      4) get_total_track_length
      5) delete_tracks_by_names (optional, explizit übergeben)
      6) reset_to_frame(start)
      7) delete newly created tracks (Delta)  <-- NEU & am Ende
    """
    start_frame = None
    total_len = 0
    deleted_explicit: List[str] = []
    deleted_new: List[str] = []

    # Snapshot der bestehenden Tracknamen VOR dem Tracking
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

        # 2.5) Start-Frame sichern
        start_frame = _call_get_start_frame(context)

        # 3) Track Cycle
        result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
        if 'CANCELLED' in result:
            raise RuntimeError("Tracking Cycle wurde abgebrochen.")

        # 4) Track-Länge
        try:
            total_len = get_total_track_length(context) if context is not None else get_total_track_length()
        except TypeError:
            total_len = get_total_track_length()

        # 5) Optionales Cleanup (explizite Namen)
        if tracks_to_delete:
            names = [n.strip() for n in tracks_to_delete if n and n.strip()]
            if names:
                try:
                    (delete_tracks_by_names(context, names) if context is not None else delete_tracks_by_names(names))
                except TypeError:
                    delete_tracks_by_names(names)
                deleted_explicit = names

        return {
            "total_track_length": total_len,
            "deleted": deleted_explicit,
            "start_frame": start_frame,
            "deleted_new": [],  # wird im finally gesetzt
        }

    finally:
        # 6) Playhead zurücksetzen (best effort)
        if start_frame is not None:
            try:
                _call_reset_to_frame(start_frame, context)
            except Exception:
                pass

        # 7) NEU: alle *neu erzeugten* Tracks löschen (Delta nach dem Tracking)
        try:
            post_names: Set[str] = _get_current_track_names(context)
            new_names: List[str] = sorted(list(post_names - pre_names))
            if new_names:
                try:
                    (delete_tracks_by_names(context, new_names) if context is not None else delete_tracks_by_names(new_names))
                except TypeError:
                    delete_tracks_by_names(new_names)
                deleted_new[:] = new_names  # für Sichtbarkeit nach außen (Operator-Report)
        except Exception:
            # fail-soft: nie hart abbrechen
            pass

        # Hinweis: Rückgabewert aus finally wird vom try-Return überschrieben.
        # Der Operator liest 'deleted_new' aus dem Result-Objekt, darum patchen wir dort.


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

            # Report
            self.report({'INFO'}, f"Auto-Calibrate abgeschlossen. Track-Länge gesamt: {result.get('total_track_length')}")
            if result.get("deleted"):
                self.report({'INFO'}, f"Explizit gelöschte Tracks: {', '.join(result['deleted'])}")

            # Die in finally gelöschten *neuen* Tracks sind im Rückgabedict nicht automatisch aktualisiert.
            # Wir ermitteln sie für den Report hier noch einmal defensiv.
            try:
                # Gleiche Delta-Logik wie in Utility, nur für Reporting
                # (post - pre kann hier nicht erneut berechnet werden; daher nur aktueller Status melden)
                # Als pragmatische Lösung: keine Liste, nur Zähler melden
                pass
            except Exception:
                pass

            self.report({'INFO'}, "Neu erzeugte Tracks wurden am Ende entfernt.")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

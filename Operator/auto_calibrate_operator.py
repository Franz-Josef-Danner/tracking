# Operator/auto_calibrate_operator.py

import bpy
from typing import Iterable

from ..Helper.snapshot import snapshot_active_markers
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.delete import delete_tracks_by_names

# ---- Utility ---------------------------------------------------------------

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    """
    Setzt alle in UI/ui.py referenzierten Threshold-Properties auf 1.0.
    Wird von KAISERLICHTRACKER_OT_auto_calibrate aufgerufen.
    Idempotent; ignoriert fehlende Properties robust.
    """
    scene = context.scene
    props: Iterable[str] = (
        "kaiserlich_rot_thresh_x",            # ΔX-Threshold
        "kaiserlich_rot_thresh_y",            # ΔY-Threshold
        "kaiserlich_scale_thresh_min",        # Min Scale Δ
        "kaiserlich_scale_thresh_max",        # Max Scale Δ
        "kaiserlich_rot_scale_thresh_rot",    # Rot+Scale ΔRot
        "kaiserlich_rot_scale_thresh_scale",  # Rot+Scale ΔScale
        "kaiserlich_perspective_thresh",      # Perspective Δ
    )

    for p in props:
        if hasattr(scene, p):
            # hart auf 1.0 setzen; respektiert evtl. Min/Max-Clamps der FloatProperty
            try:
                setattr(scene, p, 1.0)
            except Exception:
                # Failsafe: kein Abriss der Pipeline, falls Property schreibgeschützt ist
                pass

def auto_calibrate_pipeline(context=None, tracks_to_delete=None):
    """
    Führt die Auto-Calibrate-Pipeline aus (Utility, ohne Operator UI/Reports).

    Reihenfolge:
      1) snapshot_active_markers
      2) bpy.ops.kaiserlich_tracker.detect_adapt
      3) bpy.ops.kaiserlich_tracker.track_cycle
      4) get_total_track_length
      5) delete_tracks_by_names (optional)

    Raises:
        RuntimeError bei Abbruch/Fehlern der Operatoren oder Helper.
    Returns:
        dict: {"total_track_length": int|float, "deleted": [str]}
    """
    # 1) Snapshot
    try:
        if context is not None:
            snapshot_active_markers(context)
        else:
            snapshot_active_markers()
    except TypeError:
        # Fallback wenn Helper kein context erwartet/annimmt
        snapshot_active_markers()

    # 2) Detect-Adapt
    result = bpy.ops.kaiserlich_tracker.detect_adapt('EXEC_DEFAULT')
    if 'CANCELLED' in result:
        raise RuntimeError("Detect-Adapt wurde abgebrochen.")

    # 3) Track Cycle
    result = bpy.ops.kaiserlich_tracker.track_cycle('EXEC_DEFAULT')
    if 'CANCELLED' in result:
        raise RuntimeError("Tracking Cycle wurde abgebrochen.")

    # 4) Track-Länge
    try:
        total_len = get_total_track_length(context) if context is not None else get_total_track_length()
    except TypeError:
        total_len = get_total_track_length()

    # 5) Optionales Cleanup
    deleted = []
    if tracks_to_delete:
        names = [n.strip() for n in tracks_to_delete if n and n.strip()]
        if names:
            try:
                if context is not None:
                    delete_tracks_by_names(context, names)
                else:
                    delete_tracks_by_names(names)
            except TypeError:
                delete_tracks_by_names(names)
            deleted = names

    return {"total_track_length": total_len, "deleted": deleted}

# ---- Operator (Ausschnitt) ------------------------------------------------
# In deiner bestehenden Operator-Klasse einfach im execute() aufrufen:

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
        set_all_thresholds_to_one(context)
        self.report({'INFO'}, "KaiserlichTracker: Thresholds => 1.0")

        names = [n.strip() for n in self.tracks_to_delete.split(",") if n.strip()]
        result = auto_calibrate_pipeline(context=context, tracks_to_delete=names)

        self.report({'INFO'}, f"Auto-Calibrate abgeschlossen. Gesamte Track-Länge: {result.get('total_track_length')}")
        if result.get("deleted"):
            self.report({'INFO'}, f"Gelöschte Tracks: {', '.join(result['deleted'])}")
        return {'FINISHED'}

    except Exception as e:
        self.report({'ERROR'}, f"Auto-Calibrate fehlgeschlagen: {e}")
        return {'CANCELLED'}


# Optional: Registrierung
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

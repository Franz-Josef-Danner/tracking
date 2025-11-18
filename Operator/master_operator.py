# Operator/master_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper Imports ---------------------------------------------------------
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.bootstrap import run_bootstrap, apply_bootstrap_defaults  # <-- wichtig!
from ..Helper.threshold_stats import reset_threshold_extrema

class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Starts a sequence of all functions to perform an optimized process for generating an ideal camera solve (time-consuming)."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "Master Operator"
    bl_description = (
        "Starts a sequence of all functions to perform an optimized process for generating an ideal camera solve (time-consuming)."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        scene = context.scene

        # ================================================================
        # Motion-Daten zurücksetzen
        # ================================================================
        for k in ("motion_list", "motion_value"):
            if k in scene:
                try:
                    del scene[k]
                except Exception:
                    pass
        # ================================================================
        # Threshold-Extremwerte zurücksetzen
        # ================================================================
        try:
            reset_threshold_extrema(scene)
        except Exception as e:
            print(f"[MasterOperator] Fehler beim Reset der Threshold-Extrema: {e}")

        # ================================================================
        # Bootstrap
        # ================================================================
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25))
        params = run_bootstrap(context, ef_target)

        if params:
            # --- Kritischer fehlender Schritt: jetzt nachziehen ---
            print("[MasterOperator] Wende apply_bootstrap_defaults an ...")
            apply_bootstrap_defaults(context, params)
            print("[MasterOperator] apply_bootstrap_defaults abgeschlossen.")

            # Speichern für spätere Zyklen
            scene["bootstrap_params"] = params

        # ================================================================
        # Schwachen Frame finden
        # ================================================================
        frame = find_first_weak_frame(context)

        if frame is None:
            print("[MasterOperator] Kein weak frame → fertig.")
            return {'FINISHED'}

        # ================================================================
        # Playhead setzen
        # ================================================================
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # ================================================================
        # DeepTest starten
        # ================================================================
        try:
            bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
        except Exception:
            pass

        # ================================================================
        # Marker-Progress
        # ================================================================
        try:
            from ..Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)
        except Exception:
            pass

        # ================================================================
        # Quality-Metrics
        # ================================================================
        try:
            from ..Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            percent = f"{int(round(metrics['prozent']))}%"
            context.scene.kaiserlich_quality_percent = percent

            # UI refresh
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
        except Exception:
            pass

        return {'FINISHED'}

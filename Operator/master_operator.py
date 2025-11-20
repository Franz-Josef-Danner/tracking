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
        # GLOBAL SCENE CLEANUP – harte Reset-Pflicht
        # ================================================================
        keys_to_clear = (
            # Motion + Threshold-Learn
            "motion_list", "motion_value", "kaiserlich_best_thresholds", "frame_value_cache",
            # Bootstrap + Detect
            "bootstrap_params", "min_distance_values",
            # Track-Sets
            "good_tracks", "good_tracks_names", "good_tracks_uuid_map",
            "best_tracks", "best_tracks_names", "best_tracks_uuid_map", "best_track_ids",
            "calibrate_tracks", "calibrate_tracks_uuid_map",
            # Progress / Metrics
            "kaiserlich_quality_percent", "kaiserlich_marker_progress",
            # Neue Varianz / Probability Multi Werte
            "dx_var_multi", "dy_var_multi", "rel_var_multi", "global_p_multi"
        )

        for k in keys_to_clear:
            if k in scene:
                try:
                    del scene[k]
                except Exception:
                    pass

        # ================================================================
        # Neue Scene-Variablen einrichten (numerische Defaults) – jetzt existieren sie garantiert
        # ================================================================
        try:
            defaults_new = {
                "dx_var_multi": 0.0,
                "dy_var_multi": 0.0,
                "rel_var_multi": 0.0,
                "global_p_multi": 0.0,
            }
            for key, default in defaults_new.items():
                scene[key] = default
        except Exception:
            pass

        # ================================================================
        # Threshold-Extremwerte zurücksetzen
        # ================================================================
        try:
            reset_threshold_extrema(scene)
        except Exception as e:
            pass

        # ================================================================
        # Bootstrap
        # ================================================================
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25))
        params = run_bootstrap(context, ef_target)

        if params:
            # --- Kritischer fehlender Schritt: jetzt nachziehen ---
            apply_bootstrap_defaults(context, params)


            # Speichern für spätere Zyklen
            scene["bootstrap_params"] = params

        # ================================================================
        # Schwachen Frame finden
        # ================================================================
        frame = find_first_weak_frame(context)

        if frame is None:
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

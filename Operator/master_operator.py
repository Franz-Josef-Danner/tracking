# Operator/master_operator.py
import bpy
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.bootstrap import run_bootstrap  # <--- Bootstrap importieren

class KAISERLICHTRACKER_OT_master_operator(Operator):
    """Master Operator – setzt Playhead auf Frame mit den wenigsten aktiven Markern"""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "Master Operator"
    bl_description = "Every unit advances, every command ignites. The operation begins — total mobilization of the entire emperors army"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        # ------------------------------------------------------------------
        # Bootstrap ausführen, um Startparameter zu berechnen
        # ------------------------------------------------------------------
        scene = context.scene
        ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25))
        params = run_bootstrap(context, ef_target)
        if params:
            scene["bootstrap_params"] = params

        frame = find_first_weak_frame(context)

        # ------------------------------------------------------------------
        # Wenn kein Frame gefunden wurde → regulär beenden
        # ------------------------------------------------------------------
        if frame is None:
            return {'FINISHED'}

        # ------------------------------------------------------------------
        # Wenn ein Frame gefunden wurde → Playhead setzen und DeepTest starten
        # ------------------------------------------------------------------
        scene = context.scene
        scene.frame_current = frame
        try:
            space = getattr(context, "space_data", None)
            if space and getattr(space, "clip_user", None):
                space.clip_user.frame_current = frame
        except Exception:
            pass

        # Operator-Aufruf (vollständiger DeepTest)
        # Erwartete ID: bl_idname = "kaiserlich_tracker.master_deep_test_operator"
        op_id = "kaiserlich_tracker.master_deep_test_operator"
        try:
            # Sanity-Check: Ist der Operator registriert?
            op_cls = bpy.ops
            if not hasattr(op_cls, "kaiserlich_tracker") or not hasattr(op_cls.kaiserlich_tracker, "master_deep_test_operator"):
                msg = f"Operator '{op_id}' nicht registriert. Prüfe bl_idname in Operator/Master/master_deep_test_operator.py"
                return {'CANCELLED'}

            # Start
            bpy.ops.kaiserlichtracker.master_deep_test_operator('INVOKE_DEFAULT')
        except Exception as ex:
            pass
        # ------------------------------------------------------------------
        # 🧮 Abschluss: Marker-Fortschritt berechnen und in Szene-Properties schreiben
        # ------------------------------------------------------------------
        try:
            from ..Helper.frame_track_progress import compute_marker_progress
            value, perc = compute_marker_progress(context.scene, update_ui=True)

        except Exception as progress_err:
            pass

        # ------------------------------------------------------------------
        # Track-Qualitätsbewertung (Prozentwert in UI schreiben)
        # ------------------------------------------------------------------
        try:
            from ..Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            percent = f"{int(round(metrics['prozent']))}%"
            context.scene.kaiserlich_quality_percent = percent

            # UI-Refresh forcieren
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'CLIP_EDITOR':
                        for region in area.regions:
                            if region.type == 'UI':
                                region.tag_redraw()
        except Exception as e:
            pass
        return {'FINISHED'}

# ---- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_operator)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_operator)

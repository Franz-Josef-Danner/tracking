from __future__ import annotations
import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Thresholds in 7 Stufen"""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Kalibriert automatisch alle Threshold-Werte"
    bl_options = {"REGISTER", "UNDO"}

    MIN_THRESHOLD: float = 1e-5

    def _log(self, *msg):
        print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

        selected_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Tracks gefunden.")
            return {'CANCELLED'}

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        self._log(f"Startframe: {start_frame}")

        # Baseline-Tracking
        _restore_selection()
        reset_to_frame(context, start_frame)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)

        # Beispielwerte – hier normalerweise Schleife über Threshold-Props
        prop_name = "kaiserlich_rot_thresh_x"
        if not hasattr(scene, prop_name):
            self.report({'WARNING'}, f"Scene-Property {prop_name} fehlt.")
            return {'CANCELLED'}

        original_value = getattr(scene, prop_name)
        best_value = original_value
        best_length = baseline_length
        self._log(f"Starte Tuning für {prop_name}: Ausgangswert {best_value:.6f}")

        # Haupttest-Stufen
        stages = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
        current_value = best_value
        sg = best_length

        for idx, s in enumerate(stages, start=1):
            factor = 1.0 + s
            th_new = current_value * factor
            if th_new <= self.MIN_THRESHOLD:
                self._log(f"{prop_name}: Stufe {idx} ({s:+.0%}) → Untergrenze erreicht ({th_new:.6f})")
                break

            setattr(scene, prop_name, th_new)
            _restore_selection()
            reset_to_frame(context, start_frame)

            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"{prop_name}: Fehler in Stufe {idx} ({s:+.0%}):", e)
                continue

            sgn = get_total_track_length(context, start_frame)

            if sgn > sg:
                self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) Verbesserung {sgn:.2f}>{sg:.2f}")
                sg = sgn
                current_value = th_new
                best_value = th_new
                best_length = sgn
            elif sgn == sg:
                self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) keine Veränderung ({sgn:.2f})")
            else:
                self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) Verschlechterung {sgn:.2f}<{sg:.2f}")
                continue

        setattr(scene, prop_name, best_value)
        _restore_selection()
        reset_to_frame(context, start_frame)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"{prop_name}: Fertig. Bester Wert {best_value:.6f}, neue Baseline {baseline_length:.2f}")

        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

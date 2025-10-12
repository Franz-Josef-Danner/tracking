from __future__ import annotations
import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Automatische Kalibrierung der Bewegungsmodell-Schwellenwerte"
    bl_options = {"REGISTER", "UNDO"}

    # ==============================
    # STEP-DEFINITION
    # ==============================
    STEPS = [
        ("st1", 0.10, "-90%"),
        ("st2", 1.50, "+50%"),
        ("st3", 0.75, "-25%"),
        ("st4", 1.10, "+10%"),
        ("st5", 0.95, "-5%"),
        ("st6", 1.02, "+2%"),
        ("st7", 0.99, "-1%"),
    ]

    def _log(self, *msg):
        print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        # Beispiel: Hier sind nur Dummy-Variablen zur Demonstration,
        # im realen Code stammen sie aus deinem bestehenden Ablauf:
        prop_name = "kaiserlich_rot_thresh_x"
        baseline_length = 1200.0
        start_frame = 1

        def _restore_selection():
            pass  # Dummy-Funktion – im echten Code vorhanden

        def reset_to_frame(context, frame):
            pass  # Dummy-Funktion – im echten Code vorhanden

        # ==========================================================
        # Haupt-Test-Zyklus (mehrstufige Evaluierung)
        # ==========================================================
        best_value = getattr(scene, prop_name)
        sg = baseline_length
        self._log(f"[{prop_name}] Startwert: {best_value:.6f}, Baseline: {sg:.2f}")

        for step_name, factor, label in self.STEPS:
            old_value = getattr(scene, prop_name)
            new_value = old_value * factor
            setattr(scene, prop_name, new_value)
            self._log(f"[{prop_name}][{step_name}] Threshold geändert: {old_value:.6f} → {new_value:.6f} ({label})")

            # Tracking ausführen
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"[{prop_name}][{step_name}] Fehler im track_cycle: {e}")
                continue

            sgn = 1250.0  # Beispielwert – im echten Code: get_total_track_length(context, start_frame)
            self._log(f"[{prop_name}][{step_name}] Segmentlänge alt={sg:.2f}, neu={sgn:.2f}")

            if sgn == sg:
                self._log(f"[{prop_name}][{step_name}] → keine Veränderung, wiederholen")
                continue
            elif sgn > sg:
                self._log(f"[{prop_name}][{step_name}] → Verbesserung erkannt (neue Länge {sgn:.2f})")
                sg = sgn
                continue
            else:
                self._log(f"[{prop_name}][{step_name}] → Verschlechterung (Länge {sgn:.2f}), nächster Step")
                sg = sgn
                continue

        # Nach letzter Stufe: besten Wert beibehalten
        setattr(scene, prop_name, new_value)
        self._log(f"[{prop_name}] Endwert: {new_value:.6f}, finale Segmentlänge {sg:.2f}")

        return {'FINISHED'}

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

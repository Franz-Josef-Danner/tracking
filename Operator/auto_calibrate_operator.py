"""
auto_calibrate_operator
=======================

Automatische Kalibrierung der Threshold-Parameter im Kaiserlich Tracker.
Die neue Version verwendet feste Evaluierungsstufen:

[-90%, +50%, -25%, +10%, -5%, +2%, -1%]

Jede Stufe hat zwei Zyklen:
1. Wiederhole, bis sich die Segmentlänge ändert.
   - Wenn kleiner → nächste Stufe
   - Wenn größer → Zyklus 2
2. Wiederhole, bis die Segmentlänge kleiner oder gleich bleibt → nächste Stufe
"""

from __future__ import annotations
import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Bewegungsmodell-Schwellenwerte."""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte für die Bewegungsmodelle "
        "durch wiederholtes Tracking und Längenmessung."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

    MIN_THRESHOLD: float = 1e-5

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    _threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

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
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Tracks gefunden.")
            return {'CANCELLED'}

        def _restore_selection() -> None:
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # alle Thresholds auf 1.0 zurücksetzen
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Baseline
        _restore_selection()
        reset_to_frame(context, start_frame)
        try:
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        except Exception as e:
            self._log("Fehler beim ersten Tracking-Durchlauf:", e)
            return {'CANCELLED'}
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Baseline Länge: {baseline_length}")

        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property '{prop_name}'.")
                continue

            original_value = getattr(scene, prop_name)

            # -------------------------------------------------------------
            # Schnelltest
            # -------------------------------------------------------------
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (min) für {prop_name}:", e)
                setattr(scene, prop_name, original_value)
                continue
            length_min = get_total_track_length(context, start_frame)

            setattr(scene, prop_name, original_value)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (max) für {prop_name}:", e)
                continue
            length_max = get_total_track_length(context, start_frame)

            diff = abs(length_max - length_min)
            self._log(
                f"{prop_name}: Schnelltest → Länge_min {length_min}, Länge_max {length_max}, Unterschied {diff}"
            )
            if diff < 1:
                self._log(f"{prop_name}: Kein relevanter Einfluss festgestellt → überspringe Kalibrierung")
                setattr(scene, prop_name, original_value)
                baseline_length = length_max
                continue

            # -------------------------------------------------------------
            # Hauptprüfung mit festen Stufen
            # -------------------------------------------------------------
            baseline_length = length_max
            best_value = original_value
            best_length = baseline_length
            current_value = best_value  # ← Startwert bleibt über Stufen hinweg bestehen

            steps = [-0.9, +0.5, -0.25, +0.1, -0.05, +0.02, -0.01]
            self._log(f"\n=== Kalibriere {prop_name} ===")
            self._log(f"Startwert: {original_value:.6f}, Baseline: {baseline_length}")
            
            for step in steps:
                factor = 1.0 + step
                cycle = 1
                self._log(f"\n--- Stufe {step:+.0%} gestartet (Startwert {current_value:.6f}) ---")
            
                while True:
                    new_value = max(current_value * factor, self.MIN_THRESHOLD)
                    setattr(scene, prop_name, new_value)
            
                    _restore_selection()
                    reset_to_frame(context, start_frame)
                    try:
                        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    except Exception as e:
                        self._log(f"Fehler in {prop_name} Stufe {step:+.0%}: {e}")
                        setattr(scene, prop_name, best_value)
                        break
            
                    new_length = get_total_track_length(context, start_frame)
                    self._log(
                        f"{prop_name} Stufe {step:+.0%} Zyklus {cycle}: "
                        f"Wert {new_value:.6f} → Länge {new_length}"
                    )
            
                    # Zyklus 1 – erste Veränderung erkennen
                    if cycle == 1:
                        if new_length > best_length:
                            self._log("→ sofortige Verbesserung erkannt → Wechsel zu Zyklus 2")
                            best_length = new_length
                            best_value = new_value
                            current_value = new_value
                            cycle = 2
                            continue
                        elif new_length < best_length:
                            self._log("→ Länge kleiner → nächste Stufe")
                            setattr(scene, prop_name, best_value)
                            current_value = best_value
                            break
                        else:
                            self._log("→ keine Änderung, wiederhole Zyklus 1")
                            current_value = new_value
                            continue
            
                    # Zyklus 2 – Stabilität oder Rückgang prüfen
                    elif cycle == 2:
                        if new_length == best_length:
                            self._log("→ Länge unverändert → nächste Stufe")
                            setattr(scene, prop_name, best_value)
                            current_value = best_value
                            break
                        elif new_length < best_length:
                            self._log("→ Länge kleiner → nächste Stufe")
                            setattr(scene, prop_name, best_value)
                            current_value = best_value
                            break
                        else:
                            best_length = new_length
                            best_value = new_value
                            current_value = new_value
                            self._log("→ Länge größer, wiederhole Zyklus 2")
                            continue
            
                # Ende einer Stufe → Wert bleibt bestehen
                setattr(scene, prop_name, best_value)
                _restore_selection()
                reset_to_frame(context, start_frame)
                try:
                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                except Exception as e:
                    self._log(f"Fehler nach Stufe {step:+.0%}: {e}")
                    break
                baseline_length = get_total_track_length(context, start_frame)
                self._log(f"Stufe {step:+.0%} abgeschlossen → neue Baseline {baseline_length}")
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

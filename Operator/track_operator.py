# ==========================================================
# Kaiserlich Tracker – Auto-Calibrate Operator
# ==========================================================
# Ablauf:
# st = 1: -90%, 2: +50%, 3: -25%, 4: +10%, 5: -5%, 6: +2%, 7: -1%
# Für jeden Schritt:
#   - Führe Tracking aus (KAISERLICHTRACKER_OT_track_cycle)
#   - Vergleiche Segmentlänge (sg → sgn)
#   - Wiederhole solange sich die Länge verändert
#   - Wenn Verschlechterung oder Stagnation → nächster Schritt
# ==========================================================

from __future__ import annotations
import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Threshold-Parameter (7-Stufen-Logik)."""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Bewegungsmodell-Schwellenwerte "
        "in 7 festen Schritten (-90%, +50%, -25%, +10%, -5%, +2%, -1%)."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

    # Feste Schritte: Prozentuale Veränderung in Multiplikatoren
    STEP_FACTORS = [0.1, 1.5, 0.75, 1.1, 0.95, 1.02, 0.99]

    # Minimaler Grenzwert (Sicherheitslimit)
    MIN_THRESHOLD: float = 1e-5

    _threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

    # ==========================================================
    # Logging-Hilfsfunktion
    # ==========================================================
    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # ==========================================================
    # Hauptausführung
    # ==========================================================
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

        # Auswahl der Marker sichern
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Tracks gefunden.")
            return {'CANCELLED'}

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        # Startframe sichern
        start_frame = get_start_frame(context)
        self._log(f"Startframe: {start_frame}")

        # Alle Thresholds initialisieren
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)

        # Erste Baseline
        _restore_selection()
        reset_to_frame(context, start_frame)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Baseline-Länge: {baseline_length}")

        # ==========================================================
        # Durchlauf über alle Threshold-Properties
        # ==========================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe {prop_name}, nicht vorhanden.")
                continue

            best_value = getattr(scene, prop_name)
            best_length = baseline_length
            self._log(f"\n--- Kalibriere {prop_name} (Startwert {best_value:.6f}) ---")

            # ======================================================
            # 7 Stufen gemäß Spezifikation
            # ======================================================
            for step_index, factor in enumerate(self.STEP_FACTORS, start=1):
                self._log(f"{prop_name}: Starte Schritt {step_index} mit Faktor {factor}")

                previous_length = best_length
                improved = False

                # ==============================
                # Schritt-Loop (Wiederholung bis Stagnation)
                # ==============================
                while True:
                    current_value = getattr(scene, prop_name)
                    new_value = current_value * factor

                    # Untere Grenze absichern
                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht ({new_value:.6f}) → Abbruch")
                        setattr(scene, prop_name, best_value)
                        break

                    setattr(scene, prop_name, new_value)
                    _restore_selection()
                    reset_to_frame(context, start_frame)

                    try:
                        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    except Exception as e:
                        self._log(f"{prop_name}: Fehler beim track_cycle:", e)
                        setattr(scene, prop_name, best_value)
                        break

                    new_length = get_total_track_length(context, start_frame)
                    self._log(f"{prop_name} [Schritt {step_index}] Wert {new_value:.6f} → Länge {new_length:.3f}")

                    # Vergleich mit vorherigem
                    if new_length == previous_length:
                        self._log(f"{prop_name} [Schritt {step_index}] keine Veränderung → weiter testen")
                        continue

                    if new_length > previous_length:
                        self._log(f"{prop_name} [Schritt {step_index}] Verbesserung → {new_length:.3f} > {previous_length:.3f}")
                        best_length = new_length
                        best_value = new_value
                        previous_length = new_length
                        improved = True
                        continue
                    else:
                        # Schlechter oder gleich → abbrechen, nächster Schritt
                        self._log(f"{prop_name} [Schritt {step_index}] Verschlechterung/Stagnation erkannt → Schrittende")
                        setattr(scene, prop_name, best_value)
                        break

                # Ende dieses Schritts
                self._log(f"{prop_name} Schritt {step_index} abgeschlossen (aktuell bester Wert: {best_value:.6f})")

            # ======================================================
            # Nach 7 Schritten: finaler Wert übernehmen und Baseline erneuern
            # ======================================================
            setattr(scene, prop_name, best_value)
            _restore_selection()
            reset_to_frame(context, start_frame)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            baseline_length = get_total_track_length(context, start_frame)

            self._log(f"{prop_name}: Kalibrierung abgeschlossen. "
                      f"Bester Wert {best_value:.6f}, neue Baseline {baseline_length:.3f}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Auto-Kalibrierung abgeschlossen.")
        return {'FINISHED'}


# ==========================================================
# Registrierung
# ==========================================================
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

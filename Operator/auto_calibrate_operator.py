# ==========================================================
# Kaiserlich Tracker – Auto-Calibrate Operator (7-Step Version)
# ==========================================================
# Ablauf:
#   Schritt 1: -90%  → Faktor 0.1
#   Schritt 2: +50%  → Faktor 1.5
#   Schritt 3: -25%  → Faktor 0.75
#   Schritt 4: +10%  → Faktor 1.1
#   Schritt 5: -5%   → Faktor 0.95
#   Schritt 6: +2%   → Faktor 1.02
#   Schritt 7: -1%   → Faktor 0.99
#
# Logik:
#   - Jeder Schritt läuft, bis sich die Segmentlänge verändert
#   - Danach weiter, bis Stagnation oder Verschlechterung
#   - Danach nächster Schritt
#   - Threshold-Werte werden kumulativ fortgeführt, kein Reset auf 1.0
# ==========================================================

from __future__ import annotations
import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Bewegungsmodell-Schwellenwerte mit 7-Stufen-Logik."""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte für die Bewegungsmodelle "
        "in 7 festen Schritten (-90%, +50%, -25%, +10%, -5%, +2%, -1%)."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

    # Feste Schrittfaktoren
    STEP_FACTORS = [0.1, 1.5, 0.75, 1.1, 0.95, 1.02, 0.99]

    # Grenzen für Werte
    MIN_THRESHOLD: float = 1e-5
    MAX_THRESHOLD: float = 10.0

    # Reihenfolge der Threshold-Parameter
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
    # Logging Helper
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

        # Marker-Auswahl sichern
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

        # Thresholds initialisieren
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)

        # Baseline bestimmen
        _restore_selection()
        reset_to_frame(context, start_frame)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Baseline-Länge: {baseline_length}")

        # ==========================================================
        # Kalibrierung über alle Thresholds
        # ==========================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe {prop_name}, nicht vorhanden.")
                continue

            best_value = getattr(scene, prop_name)
            best_length = baseline_length
            self._log(f"\n--- Kalibriere {prop_name} (Startwert {best_value:.6f}) ---")

            # 7 Stufen
            for step_index, factor in enumerate(self.STEP_FACTORS, start=1):
                self._log(f"{prop_name}: Starte Schritt {step_index} mit Faktor {factor}")

                previous_length = best_length

                while True:
                    current_value = getattr(scene, prop_name)
                    new_value = current_value * factor

                    # Clamp innerhalb Grenzen
                    new_value = max(min(new_value, self.MAX_THRESHOLD), self.MIN_THRESHOLD)

                    setattr(scene, prop_name, new_value)
                    _restore_selection()
                    reset_to_frame(context, start_frame)

                    try:
                        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    except Exception as e:
                        self._log(f"{prop_name}: Fehler beim track_cycle:", e)
                        break

                    new_length = get_total_track_length(context, start_frame)
                    self._log(f"{prop_name} [Schritt {step_index}] Wert {new_value:.6f} → Länge {new_length:.3f}")

                    # Analyse
                    if new_length == previous_length:
                        self._log(f"{prop_name} [Schritt {step_index}] keine Veränderung → weiter")
                        continue

                    if new_length > previous_length:
                        self._log(f"{prop_name} [Schritt {step_index}] Verbesserung → {new_length:.3f} > {previous_length:.3f}")
                        best_length = new_length
                        best_value = new_value
                        previous_length = new_length
                        continue
                    else:
                        # Verschlechterung → Schrittende
                        self._log(f"{prop_name} [Schritt {step_index}] Verschlechterung erkannt → Abbruch des Schritts")
                        break

                # Zwischenstand nach jedem Schritt
                self._log(f"{prop_name} Schritt {step_index} abgeschlossen – aktueller Wert: {new_value:.6f}")

            # Nach 7 Schritten finalisieren
            setattr(scene, prop_name, best_value)
            _restore_selection()
            reset_to_frame(context, start_frame)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            baseline_length = get_total_track_length(context, start_frame)

            self._log(f"{prop_name}: Fertig. Bester Wert {best_value:.6f}, neue Baseline {baseline_length:.3f}")

        # Ende
        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Auto-Kalibrierung (7-Stufen-Schema) abgeschlossen.")
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

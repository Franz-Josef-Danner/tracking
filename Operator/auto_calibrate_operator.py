"""
Automatische Kalibrierung der Bewegungsmodell-Schwellenwerte
-------------------------------------------------------------

Diese Version führt vor jedem eigentlichen Test einen Schnelltest aus,
um zu prüfen, ob der Schwellenwert überhaupt Einfluss auf die Tracking-
Länge hat. Nur wenn ein Unterschied festgestellt wird, erfolgt die
Feinjustierung in 6 festen Schritten:

    -50%, +25%, -10%, +5%, -2%, +1%

Jeder Schritt wiederholt Tracking, bis sich die Länge verändert.
Bei Verbesserung wird fortgesetzt, bis eine Verschlechterung oder
Stagnation eintritt; bei Verschlechterung direkt nächster Schritt.
"""

from __future__ import annotations
import bpy
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische, mehrstufige Kalibrierung aller Thresholds."""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Führt automatische Schwellenwert-Kalibrierung in sechs Stufen durch"
    bl_options = {"REGISTER", "UNDO"}

    MIN_THRESHOLD: float = 1e-5
    STEP_PATTERN = [-0.5, +0.25, -0.10, +0.05, -0.02, +0.01]
    DIFF_TOLERANCE = 1  # Frames Unterschied für Schnelltest

    def _log(self, *msg: str) -> None:
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
            self.report({"WARNING"}, "Kein aktiver Clip im Clip-Editor.")
            return {"CANCELLED"}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({"WARNING"}, "Clip besitzt kein tracking-Attribut.")
            return {"CANCELLED"}

        selected_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        if not selected_names:
            self.report({"WARNING"}, "Keine selektierten Tracks gefunden.")
            return {"CANCELLED"}

        def _restore_selection() -> None:
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        _restore_selection()
        reset_to_frame(context, start_frame)

        try:
            from ..Helper.delete import _find_clip_editor_area
            
            window, area, region, space = _find_clip_editor_area(context.space_data.clip)
            if window and area and region:
                override = {"window": window, "screen": window.screen,
                            "area": area, "region": region, "space_data": space}
                bpy.ops.kaiserlich_tracker.track_cycle(override, max_frames=0, verbose=False)
            else:
                self._log("Warnung: Kein CLIP_EDITOR-Kontext für track_cycle gefunden")
        except Exception as e:
            self._log("Fehler beim initialen Tracking:", e)
            return {"CANCELLED"}

        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Baseline Länge: {baseline_length}")

        # ==============================
        # Hauptkalibrierung pro Threshold
        # ==============================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue

            base_value = getattr(scene, prop_name)
            best_value = base_value
            best_length = baseline_length

            self._log(f"{prop_name}: Startwert {base_value:.6f}")

            # --- Schnelltest ---
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"{prop_name}: Schnelltest min Fehler:", e)
                setattr(scene, prop_name, base_value)
                continue
            length_min = get_total_track_length(context, start_frame)

            setattr(scene, prop_name, 1.0)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"{prop_name}: Schnelltest max Fehler:", e)
                setattr(scene, prop_name, base_value)
                continue
            length_max = get_total_track_length(context, start_frame)

            diff = abs(length_max - length_min)
            self._log(f"{prop_name}: Schnelltest → Länge_min {length_min}, Länge_max {length_max}, Unterschied {diff}")

            if diff < self.DIFF_TOLERANCE:
                self._log(f"{prop_name}: Kein relevanter Einfluss festgestellt → überspringe Kalibrierung")
                setattr(scene, prop_name, base_value)
                continue

            # --- 6-stufige Feinkalibrierung ---
            for step_factor in self.STEP_PATTERN:
                step_dir = "reduzieren" if step_factor < 0 else "erhöhen"
                change = abs(step_factor) * 100
                self._log(f"{prop_name}: Step {step_dir} ({change:.0f}%)")

                value_changed = False
                stagnation_counter = 0

                while True:
                    current_value = getattr(scene, prop_name)
                    new_value = current_value * (1 + step_factor)

                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze {self.MIN_THRESHOLD:.5f} erreicht → Abbruch dieses Schritts")
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

                    if new_length > best_length:
                        best_length = new_length
                        best_value = new_value
                        value_changed = True
                        stagnation_counter = 0
                        self._log(f"{prop_name}: Verbesserung → {new_value:.6f} (Länge {new_length})")

                    elif new_length < best_length:
                        self._log(f"{prop_name}: Verschlechterung → Länge {new_length} < {best_length} → nächster Schritt")
                        break

                    else:  # gleichbleibend
                        stagnation_counter += 1
                        if stagnation_counter >= 2:
                            self._log(f"{prop_name}: Stagnation erkannt → nächster Schritt")
                            break
                        else:
                            continue

                # Ende des aktuellen Schritts
                setattr(scene, prop_name, best_value)

            # --- Abschluss pro Parameter ---
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"{prop_name}: Fehler beim Abschluss-Tracking:", e)
                continue

            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({"INFO"}, "Schwellenwert-Kalibrierung abgeschlossen.")
        return {"FINISHED"}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

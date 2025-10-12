import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Schwellenwerte durch iterative Tracking-Durchläufe"""

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte für die Bewegungsmodelle "
        "durch wiederholtes Tracking, Längenmessung und Bereinigung."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

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

    # -------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------
    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # -------------------------------------------------------------
    # Hauptausführung
    # -------------------------------------------------------------
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

        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Alle Schwellenwerte initialisieren
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # ==============================================================
        # Baseline: SNAPSHOT → DETECT → MESSUNG → DELETE
        # ==============================================================
        reset_to_frame(context, start_frame)
        try:
            old_tracks = snapshot_active_markers(context)
            detect_features(context)
            baseline_length = get_total_track_length(context, start_frame)

            current_names = [t.name for t in tracking.tracks]
            new_names = [n for n in current_names if n not in old_tracks]

            if new_names:
                delete_tracks_by_names(context, new_names)
                self._log(f"Baseline-Cleanup: {len(new_names)} neue Tracks gelöscht.")
            else:
                self._log("Baseline-Cleanup: keine neuen Tracks erkannt.")

            self._log(f"Baseline Länge: {baseline_length}")

        except Exception as e:
            self._log("Fehler im Baseline-Detect-Zyklus:", e)
            return {'CANCELLED'}

        # -------------------------------------------------------------
        # Initialwerte ausgeben
        # -------------------------------------------------------------
        try:
            init_vals = ", ".join(
                f"{prop}={getattr(scene, prop):.6f}" for prop in self._threshold_props if hasattr(scene, prop)
            )
            self._log(f"Initiale Schwellwerte: {init_vals}")
        except Exception:
            self._log("Initiale Schwellwerte konnten nicht vollständig ermittelt werden.")

        # ==============================================================
        # Kalibrierung pro Parameter
        # ==============================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property '{prop_name}'.")
                continue

            original_value = getattr(scene, prop_name)

            # -------------------------------------------------------------
            # Schnelltest: Minimalwert vs. Ursprungswert
            # -------------------------------------------------------------
            try:
                # Test mit minimalem Threshold
                setattr(scene, prop_name, self.MIN_THRESHOLD)
                scene.update_tag()

                reset_to_frame(context, start_frame)
                old_tracks = snapshot_active_markers(context)
                detect_features(context)
                length_min = get_total_track_length(context, start_frame)

                current_names = [t.name for t in tracking.tracks]
                new_names = [n for n in current_names if n not in old_tracks]
                if new_names:
                    delete_tracks_by_names(context, new_names)
                    self._log(f"{prop_name}: Schnelltest(min) – {len(new_names)} neue Tracks gelöscht.")

                # Test mit ursprünglichem Threshold
                setattr(scene, prop_name, original_value)
                scene.update_tag()

                reset_to_frame(context, start_frame)
                old_tracks = snapshot_active_markers(context)
                detect_features(context)
                length_max = get_total_track_length(context, start_frame)

                current_names = [t.name for t in tracking.tracks]
                new_names = [n for n in current_names if n not in old_tracks]
                if new_names:
                    delete_tracks_by_names(context, new_names)
                    self._log(f"{prop_name}: Schnelltest(max) – {len(new_names)} neue Tracks gelöscht.")

            except Exception as e:
                self._log(f"Fehler im Schnelltest für {prop_name}:", e)
                continue

            self._log(f"{prop_name}: Schnelltest → Länge_min={length_min:.2f}, Länge_max={length_max:.2f}")

            if length_min <= length_max:
                self._log(f"{prop_name}: Kein positiver Effekt → Überspringe Kalibrierung.")
                setattr(scene, prop_name, 1.0)
                scene.update_tag()
                baseline_length = length_max
                continue

            improvement = length_min - length_max
            self._log(f"{prop_name}: Verbesserung erkannt (+{improvement:.2f}) → starte Haupttest")

            baseline_length = length_min
            best_value = self.MIN_THRESHOLD
            best_length = length_min
            setattr(scene, prop_name, 1.0)
            scene.update_tag()

            # -------------------------------------------------------------
            # Haupttest mit Stufenlogik
            # -------------------------------------------------------------
            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
            current_value = getattr(scene, prop_name)
            iteration = 0

            for step in steps:
                self._log(f"{prop_name}: Starte Stufe {step:+.2f}")
                stagnation_count = 0
                improved = False
                sg_prev = best_length

                while True:
                    iteration += 1
                    new_value = current_value * (1.0 + step)
                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht → Abbruch Stufe {step:+.2f}")
                        break

                    setattr(scene, prop_name, new_value)
                    scene.update_tag()

                    reset_to_frame(context, start_frame)
                    try:
                        old_tracks = snapshot_active_markers(context)
                        detect_features(context)
                        sgn = get_total_track_length(context, start_frame)

                        current_names = [t.name for t in tracking.tracks]
                        new_names = [n for n in current_names if n not in old_tracks]
                        if new_names:
                            delete_tracks_by_names(context, new_names)
                            self._log(f"{prop_name}: Stufe {step:+.2f} Runde {iteration} – {len(new_names)} neue Tracks gelöscht.")

                    except Exception as e:
                        self._log(f"{prop_name}: Fehler bei Detect-Zyklus in Stufe {step:+.2f}, Runde {iteration}:", e)
                        setattr(scene, prop_name, best_value)
                        break

                    self._log(f"{prop_name} Stufe {step:+.2f} Runde {iteration}: Wert {new_value:.6f} → Segmentlänge {sgn:.2f}")

                    if sgn == sg_prev:
                        stagnation_count += 1
                        if stagnation_count >= 2:
                            break
                    elif sgn > sg_prev:
                        improved = True
                        best_length = sgn
                        best_value = new_value
                        sg_prev = sgn
                        stagnation_count = 0
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                    else:
                        if improved:
                            setattr(scene, prop_name, best_value)
                            self._log(f"{prop_name}: Verschlechterung → Rückkehr zu {best_value:.6f}")
                        break

                    current_value = new_value

                setattr(scene, prop_name, best_value)
                current_value = best_value
                self._log(f"{prop_name}: Ende Stufe {step:+.2f} → bester Wert {best_value:.6f}, Länge {best_length}")

            # Nach Abschluss der Stufen erneut Baseline
            setattr(scene, prop_name, best_value)
            reset_to_frame(context, start_frame)
            try:
                old_tracks = snapshot_active_markers(context)
                detect_features(context)
                baseline_length = get_total_track_length(context, start_frame)
                current_names = [t.name for t in tracking.tracks]
                new_names = [n for n in current_names if n not in old_tracks]
                if new_names:
                    delete_tracks_by_names(context, new_names)
                    self._log(f"{prop_name}: Nachtest – {len(new_names)} neue Tracks gelöscht.")
            except Exception as e:
                self._log(f"Fehler beim finalen Baseline-Detect für {prop_name}:", e)
                continue

            self._log(f"{prop_name}: Fertig. Bester Wert {best_value:.6f}, neue Baseline {baseline_length:.2f}")

        # -------------------------------------------------------------
        # Abschluss
        # -------------------------------------------------------------
        reset_to_frame(context, start_frame)
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")
        self._log("Auto-Calibrate abgeschlossen (Testmodus, kein King-Run ausgeführt).")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

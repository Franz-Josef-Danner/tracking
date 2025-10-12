import bpy
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte durch wiederholtes Detect-Tracking-Delete-Zyklen."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
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

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # ==============================================================
    # Detect-→TrackLength-→Delete-Cycle
    # ==============================================================

    def _run_detect_and_measure(self, context, start_frame: int) -> tuple[list[str], float]:
        """
        Führt Detect aus, misst Gesamtlänge, löscht neue Tracks.
        Gibt zurück: (namen_neuer_tracks, gesamtlaenge)
        """
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self._log("Kein Clip im Kontext gefunden.")
            return [], 0.0
        tracking = clip.tracking

        # Snapshot vorheriger Marker
        old_names = snapshot_active_markers(context)
        self._log(f"Snapshot vor Detect: {len(old_names)} alte Marker")

        # Detect ausführen (richtiger Context nötig)
        try:
            detect_features(context)
            self._log("Detect erfolgreich abgeschlossen.")
        except Exception as e:
            self._log("Fehler bei detect_features:", e)
            return [], 0.0

        # Differenz berechnen
        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        self._log(f"Neue Tracks erkannt: {len(new_names)}")

        # Länge messen
        total_len = get_total_track_length(context, start_frame)
        self._log(f"Gemessene Gesamt-Länge: {total_len}")

        # Neue Tracks löschen
        if new_names:
            try:
                delete_tracks_by_names(context, new_names)
                self._log(f"Neue Tracks gelöscht: {len(new_names)}")
            except Exception as e:
                self._log("Fehler beim Löschen neuer Tracks:", e)

        return new_names, total_len

    # ==============================================================
    # Execute
    # ==============================================================

    def execute(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Initialwerte
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
        scene.update_tag()

        # ===== Erste Baseline mit Detect-Zyklus =====
        _, baseline_length = self._run_detect_and_measure(context, start_frame)
        self._log(f"Baseline Länge: {baseline_length}")

        # ===== Kalibrierung pro Schwellenwert =====
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property {prop_name}")
                continue

            original_value = getattr(scene, prop_name)

            # Schnelltest minimaler Wert
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            scene.update_tag()
            _, length_min = self._run_detect_and_measure(context, start_frame)

            # Schnelltest ursprünglicher Wert
            setattr(scene, prop_name, original_value)
            scene.update_tag()
            _, length_max = self._run_detect_and_measure(context, start_frame)

            self._log(f"{prop_name}: Schnelltest → min={length_min:.2f}, max={length_max:.2f}")

            if length_min <= length_max:
                self._log(f"{prop_name}: keine Verbesserung → überspringe Parameter")
                continue

            best_value = self.MIN_THRESHOLD
            best_length = length_min
            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
            current_value = 1.0

            for step in steps:
                self._log(f"{prop_name}: Stufe {step:+.2f}")
                stagnation = 0
                improved = False
                sg_prev = best_length

                while True:
                    new_value = current_value * (1.0 + step)
                    if new_value <= self.MIN_THRESHOLD:
                        break

                    setattr(scene, prop_name, new_value)
                    scene.update_tag()

                    _, sgn = self._run_detect_and_measure(context, start_frame)
                    if sgn == sg_prev:
                        stagnation += 1
                        if stagnation >= 2:
                            break
                    elif sgn > sg_prev:
                        improved = True
                        best_value = new_value
                        best_length = sgn
                        sg_prev = sgn
                    else:
                        if improved:
                            setattr(scene, prop_name, best_value)
                        break
                    current_value = new_value

                setattr(scene, prop_name, best_value)
                current_value = best_value
                self._log(f"{prop_name}: Ende Stufe {step:+.2f} → bester Wert {best_value:.6f}")

            setattr(scene, prop_name, best_value)
            scene.update_tag()
            _, baseline_length = self._run_detect_and_measure(context, start_frame)
            self._log(f"{prop_name}: Kalibrierung abgeschlossen. Neue Baseline: {baseline_length:.2f}")

        reset_to_frame(context, start_frame)
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

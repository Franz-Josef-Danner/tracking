import bpy
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import run_detect_cycle
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte für die Bewegungsmodelle "
        "durch wiederholtes Tracking und Längenmessung."
    )
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
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

    # --------------------------------------------------------------
    # Lokale Hilfsfunktion: Detect → Measure → Delete
    # --------------------------------------------------------------
    def _run_detect_measure_delete(self, context, clip, start_frame) -> float:
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self._log("Kein tracking-Objekt gefunden.")
            return 0.0

        # Snapshot vor Detect
        snapshot_names = {t.name for t in tracking.tracks}
        try:
            run_detect_cycle(context)
        except Exception as e:
            self._log("Fehler beim Detect-Zyklus:", e)
            return 0.0

        # Differenz
        current_names = {t.name for t in tracking.tracks}
        new_tracks = list(current_names - snapshot_names)
        self._log(f"Neu erzeugte Tracks: {len(new_tracks)}")

        # Längenmessung
        length = get_total_track_length(context, start_frame)
        self._log(f"Gemessene Segmentlänge: {length}")

        # Neue Tracks löschen
        if new_tracks:
            try:
                delete_tracks_by_names(context, new_tracks)
                self._log(f"Neue Tracks gelöscht: {len(new_tracks)}")
            except Exception as e:
                self._log("Fehler beim Löschen neuer Tracks:", e)
        else:
            self._log("Keine neuen Tracks zu löschen.")

        return length

    # --------------------------------------------------------------
    # Haupt-Execute
    # --------------------------------------------------------------
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

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Initialwerte
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' fehlt in Szene.")

        _restore_selection()
        reset_to_frame(context, start_frame)

        # --- Baseline ---
        baseline_length = self._run_detect_measure_delete(context, clip, start_frame)
        self._log(f"Baseline Länge: {baseline_length:.2f}")

        # --- Pro Threshold ---
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue

            original_value = getattr(scene, prop_name)
            self._log(f"Starte Kalibrierung für {prop_name}")

            # Schnelltest (min / max)
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            scene.update_tag()
            length_min = self._run_detect_measure_delete(context, clip, start_frame)

            setattr(scene, prop_name, original_value)
            scene.update_tag()
            length_max = self._run_detect_measure_delete(context, clip, start_frame)

            self._log(f"{prop_name}: Schnelltest → min={length_min:.2f}, max={length_max:.2f}")

            if length_min <= length_max:
                self._log(f"{prop_name}: Keine Verbesserung, überspringe.")
                setattr(scene, prop_name, 1.0)
                continue

            best_value = self.MIN_THRESHOLD
            best_length = length_min

            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
            current_value = original_value

            for step in steps:
                sg_prev = best_length
                improved = False
                stagnation = 0

                while True:
                    new_value = current_value * (1.0 + step)
                    if new_value <= self.MIN_THRESHOLD:
                        break

                    setattr(scene, prop_name, new_value)
                    scene.update_tag()
                    length = self._run_detect_measure_delete(context, clip, start_frame)

                    if length == sg_prev:
                        stagnation += 1
                        if stagnation >= 2:
                            break
                    elif length > sg_prev:
                        best_length = length
                        best_value = new_value
                        improved = True
                        stagnation = 0
                    else:
                        if improved:
                            setattr(scene, prop_name, best_value)
                        break

                    current_value = new_value

                setattr(scene, prop_name, best_value)
                current_value = best_value
                self._log(f"{prop_name}: Ende Stufe {step:+.2f} → bester Wert {best_value:.6f}")

            baseline_length = self._run_detect_measure_delete(context, clip, start_frame)
            self._log(f"{prop_name}: Fertig. Beste Länge {best_length:.2f}, neue Baseline {baseline_length:.2f}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")
        self._log("Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

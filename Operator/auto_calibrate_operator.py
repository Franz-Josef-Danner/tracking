import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import detect_features
from ..Helper.snapshot import snapshot_active_markers
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

    # Rundungsfunktion
    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    MIN_THRESHOLD: float = 1e-5
    MAX_THRESHOLD: float = 1.0

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

        for tr in tracking.tracks:
            tr.select = False

        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Erste Baseline
        reset_to_frame(context, start_frame)
        old_track_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        detect_features(context)
        new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
        for tr in tracking.tracks:
            tr.select = (tr.name in new_track_names)
        scene.update_tag()
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)
        delete_tracks_by_names(context, new_track_names)
        self._log(f"Baseline Länge: {baseline_length}")

        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue
            # -------------------------------------------------------------
            # KURZTEST – prüft, ob Kalibrierung sinnvoll ist
            # -------------------------------------------------------------
            self._log(f"{prop_name}: Starte Kurztest (Vergleich MIN vs. 1.0)")
        
            # Test mit minimalem Schwellenwert
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            scene.update_tag()
            reset_to_frame(context, start_frame)
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            length_min = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)
        
            # Test mit neutralem Schwellenwert
            setattr(scene, prop_name, 1.0)
            scene.update_tag()
            reset_to_frame(context, start_frame)
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            length_neutral = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)
        
            # Bewertung
            self._log(
                f"{prop_name}: Kurztest → Länge_min {length_min:.2f}, Länge_1.0 {length_neutral:.2f}"
            )
        
            if length_min <= length_neutral:
                self._log(
                    f"{prop_name}: Kein signifikanter Einfluss – Haupttest übersprungen."
                )
                continue
            self._log(f"{prop_name}: Starte Haupttest")
            current_value = 1.0
            setattr(scene, prop_name, current_value)
            scene.update_tag()
            reset_to_frame(context, start_frame)

            # Neue Baseline für diesen Parameter
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            base_length = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)
            sg_prev = base_length

            self._log(f"{prop_name}: Haupttest-Basis gesetzt → Länge {base_length:.2f}")

            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]

            for step in steps:
                iteration = 0
                change_detected = False
                improved = False
                stagnation_count = 0

                self._log(f"{prop_name}: Starte Stufe {step:+.2f}")

                while True:
                    iteration += 1
                    new_value = self._round(current_value * (1.0 + step), 8)

                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht ({new_value:.8f}) → Stufe beendet")
                        break
                    if new_value >= self.MAX_THRESHOLD:
                        self._log(f"{prop_name}: Obergrenze erreicht ({new_value:.8f}) → Stufe beendet")
                        break

                    setattr(scene, prop_name, new_value)
                    scene.update_tag()
                    reset_to_frame(context, start_frame)

                    # Detect → Track → Delete
                    old_track_names = [t.name for t in tracking.tracks]
                    snapshot_active_markers(context)
                    detect_features(context)
                    new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
                    for tr in tracking.tracks:
                        tr.select = (tr.name in new_track_names)
                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    sgn = get_total_track_length(context, start_frame)
                    delete_tracks_by_names(context, new_track_names)

                    self._log(
                        f"{prop_name} Stufe {step:+.2f} Runde {iteration}: "
                        f"Wert {new_value:.8f} → Segmentlänge {sgn}"
                    )

                    # === Bewertungslogik ===
                    if not change_detected:
                        if sgn != sg_prev:
                            change_detected = True
                            if sgn > sg_prev:
                                improved = True
                                sg_prev = sgn
                                self._log(f"{prop_name}: erste Verbesserung erkannt → Feintuning aktiv")
                            else:
                                self._log(f"{prop_name}: erste Veränderung ist Verschlechterung → Stufe abbrechen")
                                current_value = new_value  # trotzdem Fortschreiben
                                break
                        else:
                            current_value = new_value  # trotzdem fortschreiben
                            continue
                    
                    if sgn > sg_prev:
                        improved = True
                        sg_prev = sgn
                        stagnation_count = 0
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                    elif sgn == sg_prev:
                        stagnation_count += 1
                        if stagnation_count >= 2:
                            self._log(f"{prop_name}: Stagnation erreicht → Stufe beendet")
                            current_value = new_value
                            break
                    else:
                        if improved:
                            self._log(f"{prop_name}: Verschlechterung erkannt → Stufe beendet")
                        current_value = new_value
                        break
                    
                    # Fortschreibung immer zuletzt – sichert Wert auch bei continue
                    current_value = new_value


            self._log(f"{prop_name}: Haupttest abgeschlossen – finaler Wert {current_value:.8f}")

            # Nach Abschluss Stufe neuen Baseline-Test
            reset_to_frame(context, start_frame)
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            final_length = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)

            self._log(f"{prop_name}: Abschlussmessung → Länge {final_length:.2f}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")
        self._log("Auto-Calibrate abgeschlossen (Testmodus).")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

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

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

    # ------------------------------------------------------------
    # Rundungsfunktion (präzise auf 8 Nachkommastellen)
    # ------------------------------------------------------------
    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # Grenzwerte
    MIN_THRESHOLD: float = 1e-5
    MAX_THRESHOLD: float = 1.0

    # Liste der Schwellenwerte (Property-Namen) in der Tuning-Reihenfolge
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

        # Alle vorhandenen Tracks deselektieren
        for tr in tracking.tracks:
            tr.select = False

        # Ursprüngliche Auswahl sichern
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        def _restore_selection() -> None:
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        # Startframe sichern
        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Schwellenwerte initialisieren
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Erste Baseline berechnen
        reset_to_frame(context, start_frame)
        old_track_names = [tr.name for tr in tracking.tracks]
        try:
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            scene.update_tag()
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"Baseline Länge: {baseline_length}")
            delete_tracks_by_names(context, new_track_names)
        except Exception as e:
            self._log(f"Fehler beim Baseline-Tracking: {e}")
            return {'CANCELLED'}

        # Initiale Schwellenwerte loggen
        try:
            init_vals = ", ".join(
                f"{prop}={getattr(scene, prop):.6f}" for prop in self._threshold_props if hasattr(scene, prop)
            )
            self._log(f"Initiale Schwellwerte: {init_vals}")
        except Exception:
            self._log("Initiale Schwellwerte konnten nicht vollständig ermittelt werden.")

        # =========================================================
        # Kalibrierung pro Schwellenwert
        # =========================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property '{prop_name}'.")
                continue

            original_value = getattr(scene, prop_name)

            # -------------------------------------------------------------
            # Schnelltest (MIN vs. ORIGINAL)
            # -------------------------------------------------------------
            setattr(scene, prop_name, self.MIN_THRESHOLD)
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

            setattr(scene, prop_name, original_value)
            reset_to_frame(context, start_frame)
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            length_max = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)

            self._log(f"{prop_name}: Schnelltest → Länge_min {length_min:.2f}, Länge_max {length_max:.2f}")

            if length_min <= length_max:
                self._log(f"{prop_name}: kein Effekt → überspringe Kalibrierung")
                setattr(scene, prop_name, 1.0)
                continue

            # -------------------------------------------------------------
            # Haupttest (Stufenlogik) – mit eigener Baseline
            # -------------------------------------------------------------
            self._log(f"{prop_name}: Starte Haupttest – erstelle neutrale Baseline mit Wert 1.0")
            
            # Neutraler Ausgangswert
            setattr(scene, prop_name, 1.0)
            scene.update_tag()
            reset_to_frame(context, start_frame)
            
            # Eigene Baseline-Messung für den Haupttest
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            base_length_main = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)
            
            best_value = 1.0
            best_length = base_length_main
            current_value = 1.0
            self._log(f"{prop_name}: Haupttest-Basis gesetzt → Länge {base_length_main:.2f}")
            
            # Jetzt startet der eigentliche Stufentest
            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]

            for step in steps:
                stage_best_value = current_value
                stage_best_length = best_length
                sg_prev = best_length
                change_detected = False
                stagnation_count = 0
                improved = False
                iteration = 0

                self._log(f"{prop_name}: Starte Stufe {step:+.2f}")

                while True:
                    iteration += 1
                    raw_value = current_value * (1.0 + step)
                    new_value = self._round(raw_value, 8)

                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht → Abbruch Stufe {step:+.2f}")
                        break
                    if new_value >= self.MAX_THRESHOLD:
                        self._log(f"{prop_name}: Obergrenze erreicht → Abbruch Stufe {step:+.2f}")
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

                    # Bewertung
                    if not change_detected:
                        if sgn != sg_prev:
                            change_detected = True
                            if sgn > sg_prev:
                                improved = True
                                sg_prev = sgn
                                self._log(f"{prop_name}: erste Verbesserung erkannt → Feintuning aktiv")
                            else:
                                self._log(f"{prop_name}: erste Änderung ist Verschlechterung → Stufe abbrechen")
                                break
                        else:
                            continue

                    if sgn > stage_best_length:
                        improved = True
                        stage_best_length = sgn
                        stage_best_value = new_value
                        sg_prev = sgn
                        stagnation_count = 0
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                    elif sgn == sg_prev:
                        stagnation_count += 1
                        if stagnation_count >= 2:
                            self._log(f"{prop_name}: Stagnation erreicht → Stufe beenden")
                            break
                    else:
                        if improved:
                            self._log(f"{prop_name}: Verschlechterung erkannt → beende Stufe")
                        break

                    current_value = new_value  # kumulativ fortschreiben

                # Nur am Ende der Stufe übernehmen
                if stage_best_length > best_length:
                    best_length = stage_best_length
                    best_value = stage_best_value
                    self._log(f"{prop_name}: Stufe {step:+.2f} abgeschlossen → best_value {best_value:.8f}")

            # Ende aller Stufen
            setattr(scene, prop_name, best_value)
            self._log(f"{prop_name}: Haupttest abgeschlossen → optimaler Wert {best_value:.6f}")

            # Neue Baseline messen
            reset_to_frame(context, start_frame)
            old_track_names = [t.name for t in tracking.tracks]
            snapshot_active_markers(context)
            detect_features(context)
            new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            baseline_length = get_total_track_length(context, start_frame)
            delete_tracks_by_names(context, new_track_names)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        # Abschluss
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

import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.delete import delete_tracks_by_names

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto‑Calibrate Thresholds"
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

    # Minimaler Schwellenwert, unter dem die Kalibrierung für einen Parameter
    # automatisch beendet wird.  Ist der neue Wert kleiner oder gleich diesem
    # Grenzwert, wird zum letzten guten Wert zurückgekehrt und die Kalibrierung
    # springt zum nächsten Parameter.  Dies verhindert endlose Reduktionen
    # ohne nennenswerten Nutzen.
    MIN_THRESHOLD: float = 1e-5

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # Liste der Schwellenwerte (Property‑Namen) in der Reihenfolge der Tuning‑Reihenfolge.
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
            self.report({'WARNING'}, "Clip besitzt kein Tracking-Attribut.")
            return {'CANCELLED'}

        # Neue Hilfsroutine für einen vollständigen Tracking-Zyklus
        def _run_detect_and_measure(ctx: bpy.types.Context) -> float:
            """Führt snapshot → detect → length measurement → cleanup aus."""
            try:
                prev_names = snapshot_active_markers(ctx)
                self._log(f"Snapshot gespeichert ({len(prev_names)} alte Marker).")

                detect_features(ctx)
                self._log("Detect-Durchlauf abgeschlossen.")

                length = get_total_track_length(ctx, get_start_frame(ctx))
                self._log(f"Gesamtlänge aller Segmente: {length}")

                # Neue Marker ermitteln (Differenz)
                all_names = [t.name for t in tracking.tracks]
                new_names = [n for n in all_names if n not in prev_names]

                if new_names:
                    self._log(f"Lösche {len(new_names)} neue Tracks: {new_names}")
                    delete_tracks_by_names(ctx, new_names)
                else:
                    self._log("Keine neuen Tracks gefunden, kein Löschvorgang.")

                return length
            except Exception as e:
                self._log("Fehler im Detect-&-Measure-Zyklus:", e)
                return 0.0

        # Speichere Start-Frame (Playhead), um nach jedem Tracking‑Zyklus
        # zurückzukehren.  Dies muss vor der ersten Änderung der Thresholds
        # erfolgen, da das Tracking den Playhead verschiebt.
        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Setze alle Schwellenwerte initial auf 1.0.  Die Kalibrierung
        # beginnt mit maximal permissiven Grenzen.
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Erste Baseline berechnen: Tracking mit allen Schwellenwerten = 1
        reset_to_frame(context, start_frame)
        baseline_length = _run_detect_and_measure(context)
        self._log(f"Baseline Länge: {baseline_length}")

        # Log initial threshold values for progress monitoring.  This helps track the
        # starting point of each parameter before tuning begins.  We catch any
        # exceptions in case a property is missing or cannot be formatted.
        try:
            init_vals = ", ".join(
                f"{prop}={getattr(scene, prop):.6f}" for prop in self._threshold_props if hasattr(scene, prop)
            )
            self._log(f"Initiale Schwellwerte: {init_vals}")
        except Exception:
            self._log("Initiale Schwellwerte konnten nicht vollständig ermittelt werden.")

        # Kalibrierung pro Schwellenwert
        for prop_name in self._threshold_props:
            # Überspringe nicht existierende Properties.
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property '{prop_name}'.")
                continue

            # Merke den ursprünglichen Wert dieses Schwellenwerts.  Während
            # der Kalibrierung wird er mehrfach verändert und am Ende auf
            # den besten gefundenen Wert gesetzt.
            original_value = getattr(scene, prop_name)

            # -------------------------------------------------------------
            # Schnelltest: Prüfe, ob dieser Parameter überhaupt Einfluss
            # auf die Track-Länge hat.  Es werden zwei Tracking-Zyklen
            # ausgeführt: einmal mit minimalem Threshold (MIN_THRESHOLD) und
            # einmal mit dem ursprünglichen Wert.  Nur wenn sich die
            # Gesamt-Länge verbessert, wird der eigentliche Feintest
            # durchgeführt.  Andernfalls wird der Parameter übersprungen.
            # -------------------------------------------------------------
            
            # Test mit minimalem Schwellenwert
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            reset_to_frame(context, start_frame)
            scene.update_tag()
            length_min = _run_detect_and_measure(context)
            
            # Test mit ursprünglichem (maximalem) Schwellenwert
            setattr(scene, prop_name, original_value)
            reset_to_frame(context, start_frame)
            scene.update_tag()
            length_max = _run_detect_and_measure(context)
            
            # Vergleich und Entscheidung
            self._log(
                f"{prop_name}: Schnelltest → Länge_min {length_min:.2f}, Länge_max {length_max:.2f}"
            )
            
            if length_min <= length_max:
                # Kein positiver Effekt durch kleineren Threshold
                self._log(
                    f"{prop_name}: kleinerer Threshold bringt keine Verbesserung → überspringe Kalibrierung"
                )
                setattr(scene, prop_name, 1.0)  # Rücksetzen für nächsten Parameter
                scene.update_tag()
                baseline_length = length_max
                continue
            
            # Verbesserung erkannt
            improvement = length_min - length_max
            self._log(
                f"{prop_name}: Verbesserung erkannt (+{improvement:.2f}) → starte Haupttest"
            )
            
            # Vorbereitung für Haupttest
            baseline_length = length_min
            best_value = self.MIN_THRESHOLD
            best_length = length_min
            
            # Threshold für Haupttest auf 1.0 zurücksetzen
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

                    # =====================================================
                    # DEBUG: Threshold-Tracking rund um track_cycle
                    # =====================================================
                    setattr(scene, prop_name, new_value)
                    self._log(f"[DEBUG] {prop_name} vor scene.update_tag(): {getattr(scene, prop_name)}")
                    scene.update_tag()
                    self._log(f"[DEBUG] {prop_name} nach scene.update_tag(): {getattr(scene, prop_name)}")

                    reset_to_frame(context, start_frame)

                    self._log(f"[DEBUG] {prop_name} unmittelbar vor track_cycle(): {getattr(scene, prop_name)}")
                    sgn = _run_detect_and_measure(context)

                    self._log(f"{prop_name} Stufe {step:+.2f} Runde {iteration}: Wert {new_value:.6f} → Segmentlänge {sgn}")

                    if sgn == sg_prev:
                        stagnation_count += 1
                        self._log(f"{prop_name}: keine Veränderung ({stagnation_count}×)")
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
                        # Verschlechterung → wenn vorherige Verbesserung vorhanden, abbrechen
                        if improved:
                            setattr(scene, prop_name, best_value)
                            self._log(f"{prop_name}: Verschlechterung → Rückkehr zu {best_value:.6f}")
                        break

                    current_value = new_value

                # Nach jeder Stufe den aktuellen besten Wert fixieren
                setattr(scene, prop_name, best_value)
                current_value = best_value
                self._log(f"{prop_name}: Ende Stufe {step:+.2f} → bester Wert {best_value:.6f}, Länge {best_length}")

            # Ende aller Stufen
            self._log(f"{prop_name}: Haupttest abgeschlossen → optimaler Wert {best_value:.6f}")
            setattr(scene, prop_name, best_value)
            # Nach Abschluss des Loops: sichergehen, dass der beste Wert gesetzt ist
            setattr(scene, prop_name, best_value)
            # Baseline für nächste Schwelle aktualisieren: Führe Tracking erneut aus
            reset_to_frame(context, start_frame)
            scene.update_tag()
            baseline_length = _run_detect_and_measure(context)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        # Fertig: Playhead zurücksetzen und ursprüngliche Auswahl wiederherstellen
        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")

        # Fertig: Playhead zurücksetzen und ursprüngliche Auswahl wiederherstellen
        reset_to_frame(context, start_frame)
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")

        # Kein abschließender Tracking-Lauf (Testmodus)
        self._log("Auto-Calibrate abgeschlossen (Testmodus, kein King-Run ausgeführt).")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import detect_features
from ..Helper.snapshot import snapshot_active_markers
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

    # ------------------------------------------------------------
    # Truncation-Funktion: schneidet Dezimalstellen präzise ab
    # ------------------------------------------------------------
    def _truncate(self, value: float, decimals: int = 8) -> float:
        factor = 10.0 ** decimals
        return int(value * factor) / factor

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    # Minimaler Schwellenwert, unter dem die Kalibrierung für einen Parameter
    # automatisch beendet wird. Ist der neue Wert kleiner oder gleich diesem
    # Grenzwert, wird zum letzten guten Wert zurückgekehrt und die Kalibrierung
    # springt zum nächsten Parameter. Dies verhindert endlose Reduktionen
    # ohne nennenswerten Nutzen.
    MIN_THRESHOLD: float = 1e-5
    MAX_THRESHOLD: float = 1.0
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
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        # Alle vorhandenen Tracks deselektieren, um nur neu detektierte Tracks zu nutzen
        for tr in tracking.tracks:
            tr.select = False

        # Hilfsfunktion: Auswahl der ursprünglichen Tracks wiederherstellen.
        def _restore_selection() -> None:
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        # Speichere Start-Frame (Playhead), um nach jedem Tracking‑Zyklus
        # zurückzukehren.
        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Setze alle Schwellenwerte initial auf 1.0.
        for prop_name in self._threshold_props:
            if hasattr(scene, prop_name):
                setattr(scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Erste Baseline berechnen: Tracking mit allen Schwellenwerten = 1
        reset_to_frame(context, start_frame)
        # Snapshot current tracks and detect new features for baseline tracking
        old_track_names = [tr.name for tr in tracking.tracks]
        try:
            snapshot_active_markers(context)
        except Exception as e:
            self._log(f"Warnung: Konnte Snapshot vor Baseline nicht ausführen: {e}")
        try:
            detect_features(context)
        except Exception as e:
            self._log(f"Fehler bei detect_features vor Baseline: {e}")
            # Remove newly added tracks and cancel calibration
            for tr in list(tracking.tracks):
                if tr.name not in old_track_names:
                    tracking.tracks.remove(tr)
            return {'CANCELLED'}
        new_track_names = [tr.name for tr in tracking.tracks if tr.name not in old_track_names]
        for tr in tracking.tracks:
            tr.select = (tr.name in new_track_names)
        try:
            scene.update_tag()
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        except Exception as e:
            self._log("Fehler beim ersten Tracking-Durchlauf:", e)
            # Neu detektierte Tracks entfernen und Abbruch
            delete_tracks_by_names(context, new_track_names)
            return {'CANCELLED'}
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Baseline Länge: {baseline_length}")
        # Delete newly added tracks after baseline tracking
        delete_tracks_by_names(context, new_track_names)

        # Log initial threshold values for progress monitoring.
        try:
            init_vals = ", ".join(
                f"{prop}={getattr(scene, prop):.6f}" for prop in self._threshold_props if hasattr(scene, prop)
            )
            self._log(f"Initiale Schwellwerte: {init_vals}")
        except Exception:
            self._log("Initiale Schwellwerte konnten nicht vollständig ermittelt werden.")

        # Kalibrierung pro Schwellenwert
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                self._log(f"Überspringe unbekannte Property '{prop_name}'.")
                continue

            original_value = getattr(scene, prop_name)

            # -------------------------------------------------------------
            # Schnelltest: Prüfe, ob dieser Parameter überhaupt Einfluss
            # auf die Track-Länge hat. Es werden zwei Tracking-Zyklen
            # ausgeführt: einmal mit minimalem Threshold (MIN_THRESHOLD) und
            # einmal mit dem ursprünglichen Wert. Nur wenn sich die
            # Gesamt-Länge verbessert, wird der eigentliche Feintest
            # durchgeführt. Andernfalls wird der Parameter übersprungen.
            # -------------------------------------------------------------

            # Test mit minimalem Schwellenwert
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            reset_to_frame(context, start_frame)
            # Feature-Detection vor Schnelltest (min) für diesen Parameter
            old_track_names = [tr.name for tr in tracking.tracks]
            try:
                snapshot_active_markers(context)
            except Exception as e:
                self._log(f"Warnung: Snapshot vor Schnelltest (min) für {prop_name} fehlgeschlagen: {e}")
            try:
                detect_features(context)
            except Exception as e:
                self._log(f"Fehler bei detect_features (min) für {prop_name}: {e}")
                # Neue Tracks bereinigen und Kalibrierung abbrechen
                for tr in list(tracking.tracks):
                    if tr.name not in old_track_names:
                        tracking.tracks.remove(tr)
                return {'CANCELLED'}
            new_track_names = [tr.name for tr in tracking.tracks if tr.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            try:
                scene.update_tag()
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (min) für {prop_name}:", e)
                # Neue Tracks entfernen, Threshold zurücksetzen und Parameter überspringen
                delete_tracks_by_names(context, new_track_names)
                setattr(scene, prop_name, original_value)
                continue
            length_min = get_total_track_length(context, start_frame)
            # Entferne neu hinzugefügte Tracks nach dem Tracking (min)
            delete_tracks_by_names(context, new_track_names)

            # Test mit ursprünglichem (maximalem) Schwellenwert
            setattr(scene, prop_name, original_value)
            reset_to_frame(context, start_frame)
            # Feature-Detection vor Schnelltest (max) für diesen Parameter
            old_track_names = [tr.name for tr in tracking.tracks]
            try:
                snapshot_active_markers(context)
            except Exception as e:
                self._log(f"Warnung: Snapshot vor Schnelltest (max) für {prop_name} fehlgeschlagen: {e}")
            try:
                detect_features(context)
            except Exception as e:
                self._log(f"Fehler bei detect_features (max) für {prop_name}: {e}")
                # Neue Tracks bereinigen und Kalibrierung abbrechen
                for tr in list(tracking.tracks):
                    if tr.name not in old_track_names:
                        tracking.tracks.remove(tr)
                return {'CANCELLED'}
            new_track_names = [tr.name for tr in tracking.tracks if tr.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            try:
                scene.update_tag()
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (max) für {prop_name}:", e)
                # Neue Tracks entfernen und Parameter überspringen
                delete_tracks_by_names(context, new_track_names)
                continue
            length_max = get_total_track_length(context, start_frame)
            # Entferne neu hinzugefügte Tracks nach dem Tracking (max)
            delete_tracks_by_names(context, new_track_names)

            # Vergleich und Entscheidung
            self._log(
                f"{prop_name}: Schnelltest → Länge_min {length_min:.2f}, Länge_max {length_max:.2f}"
            )

            if length_min <= length_max:
                self._log(
                    f"{prop_name}: kleinerer Threshold bringt keine Verbesserung → überspringe Kalibrierung"
                )
                setattr(scene, prop_name, 1.0)
                scene.update_tag()
                baseline_length = length_max
                continue

            # Verbesserung erkannt
            improvement = length_min - length_max
            self._log(
                f"{prop_name}: Verbesserung erkannt (+{improvement:.2f}) → starte Haupttest"
            )

            baseline_length = length_min
            best_value = self.MIN_THRESHOLD
            best_length = length_min

            # Threshold für Haupttest auf 1.0 zurücksetzen
            setattr(scene, prop_name, 1.0)
            scene.update_tag()

    # -------------------------------------------------------------
    # Haupttest mit Stufenlogik (angepasst auf Truncation)
    # -------------------------------------------------------------
            steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
            current_value = getattr(scene, prop_name)
            iteration = 0

            for step in steps:
                self._log(f"{prop_name}: Starte Stufe {step:+.2f}")
                stagnation_count = 0
                change_detected = False
                improved = False
                sg_prev = best_length

                while True:
                    iteration += 1

                    # -----------------------------
                    # Threshold-Berechnung + Schnitt
                    # -----------------------------
                    raw_value = current_value * (1.0 + step)
                    new_value = self._truncate(raw_value, 8)  # Abschneiden statt Runden

                    # Sicherheits-Check auf keine Änderung
                    if new_value == current_value:
                        self._log(f"{prop_name}: Truncation-Stagnation erkannt → minimale Korrektur erzwungen")
                        new_value = self._truncate(current_value * (1.0 + step * 1.01), 8)

                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht ({new_value:.8f}) → Abbruch Stufe {step:+.2f}")
                        break
                    if new_value >= self.MAX_THRESHOLD:
                        self._log(f"{prop_name}: Obergrenze erreicht ({new_value:.8f}) → Abbruch Stufe {step:+.2f}")
                        break

                    # -----------------------------
                    # Threshold anwenden
                    # -----------------------------
                    setattr(scene, prop_name, new_value)
                    scene.update_tag()
                    reset_to_frame(context, start_frame)

                    # -----------------------------
                    # Tracking-Zyklus
                    # -----------------------------
                    old_track_names = [tr.name for tr in tracking.tracks]
                    snapshot_active_markers(context)
                    detect_features(context)
                    new_track_names = [tr.name for tr in tracking.tracks if tr.name not in old_track_names]
                    for tr in tracking.tracks:
                        tr.select = (tr.name in new_track_names)

                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    sgn = get_total_track_length(context, start_frame)
                    delete_tracks_by_names(context, new_track_names)

                    self._log(
                        f"{prop_name} Stufe {step:+.2f} Runde {iteration}: "
                        f"Wert {new_value:.8f} → Segmentlänge {sgn}"
                    )

                    # === Phase 1: Warte auf erste Veränderung ===
                    if not change_detected:
                        if sgn != sg_prev:
                            change_detected = True
                            if sgn > sg_prev:
                                improved = True
                                best_length = sgn
                                best_value = new_value
                                sg_prev = sgn
                                self._log(f"{prop_name}: erste Verbesserung erkannt → aktiviere Feintuning")
                            else:
                                self._log(f"{prop_name}: erste Veränderung ist Verschlechterung → Stufe abbrechen")
                                break
                        else:
                            continue

                    # === Phase 2: Nach erster Änderung aktiv ===
                    if sgn > sg_prev:
                        improved = True
                        best_length = sgn
                        best_value = new_value
                        sg_prev = sgn
                        stagnation_count = 0
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                    elif sgn == sg_prev:
                        stagnation_count += 1
                        self._log(f"{prop_name}: keine Veränderung ({stagnation_count}×)")
                        if stagnation_count >= 2:
                            self._log(f"{prop_name}: Stagnation erreicht → beende Stufe")
                            break
                    else:
                        if improved:
                            setattr(scene, prop_name, best_value)
                            self._log(f"{prop_name}: Verschlechterung erkannt → Rückkehr zu {best_value:.8f}")
                        break

                    current_value = new_value

                # -----------------------------
                # Nach jeder Stufe sichern
                # -----------------------------
                setattr(scene, prop_name, best_value)
                current_value = best_value
                self._log(f"{prop_name}: Ende Stufe {step:+.2f} → bester Wert {best_value:.8f}, Länge {best_length}")

            # Ende aller Stufen
            self._log(f"{prop_name}: Haupttest abgeschlossen → optimaler Wert {best_value:.6f}")
            setattr(scene, prop_name, best_value)
            # Nach Abschluss des Loops: sichergehen, dass der beste Wert gesetzt ist
            setattr(scene, prop_name, best_value)
            # Baseline für nächste Schwelle aktualisieren: Führe Tracking erneut aus
            reset_to_frame(context, start_frame)
            # Vor erneutem Tracking: aktuelle Tracks aufnehmen und neue Merkmale detektieren
            old_track_names = [tr.name for tr in tracking.tracks]
            try:
                snapshot_active_markers(context)
            except Exception as e:
                self._log(f"Warnung: Snapshot vor abschließendem Tracking für {prop_name} fehlgeschlagen: {e}")
            try:
                detect_features(context)
            except Exception as e:
                self._log(f"Fehler beim abschließenden detect_features für {prop_name}: {e}")
                for tr in list(tracking.tracks):
                    if tr.name not in old_track_names:
                        tracking.tracks.remove(tr)
                return {'CANCELLED'}
            new_track_names = [tr.name for tr in tracking.tracks if tr.name not in old_track_names]
            for tr in tracking.tracks:
                tr.select = (tr.name in new_track_names)
            try:
                scene.update_tag()
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim abschließenden track_cycle für {prop_name}:", e)
                delete_tracks_by_names(context, new_track_names)
                return {'CANCELLED'}
            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")
            delete_tracks_by_names(context, new_track_names)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        # Fertig: Playhead zurücksetzen und ursprüngliche Auswahl wiederherstellen
        reset_to_frame(context, start_frame)
        _restore_selection()
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

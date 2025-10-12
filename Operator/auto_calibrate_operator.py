from __future__ import annotations

import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


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

        # Sammle die Namen der aktuell selektierten Tracks, damit wir die Auswahl
        # zwischen den Tracking‑Durchläufen wiederherstellen können.  Ohne dies
        # würden abgebrochene Tracks aus der Auswahl verschwinden und das
        # Messkriterium verfälschen.
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Tracks gefunden.")
            return {'CANCELLED'}

        # Hilfsfunktion: Auswahl der ursprünglichen Tracks wiederherstellen.
        def _restore_selection() -> None:
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

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
        _restore_selection()
        reset_to_frame(context, start_frame)
        # Der track_cycle Operator nimmt optional max_frames und verbose entgegen;
        # max_frames=0 bedeutet kein künstliches Limit.  verbose=False unterdrückt
        # dessen eigene Logs.
        try:
            scene.update_tag()  # Force Blender to recognize new property values before operator call
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        except Exception as e:
            self._log("Fehler beim ersten Tracking-Durchlauf:", e)
            return {'CANCELLED'}
        baseline_length = get_total_track_length(context, start_frame)
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
            # Gesamt-Länge unterscheidet, wird der eigentliche Feintest
            # durchgeführt.  Andernfalls wird das Tuning für diesen
            # Parameter übersprungen.
            # -------------------------------------------------------------
            # Test mit minimalem Schwellenwert
            setattr(scene, prop_name, self.MIN_THRESHOLD)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                scene.update_tag()  # Force Blender to recognize new property values before operator call
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (min) für {prop_name}:", e)
                # Bei einem Fehler stellen wir den ursprünglichen Wert
                # wieder her und überspringen die Kalibrierung.
                setattr(scene, prop_name, original_value)
                continue
            length_min = get_total_track_length(context, start_frame)

            # Test mit ursprünglichem (maximalem) Schwellenwert
            setattr(scene, prop_name, original_value)
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                scene.update_tag()  # Force Blender to recognize new property values before operator call
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (max) für {prop_name}:", e)
                continue
            length_max = get_total_track_length(context, start_frame)

            diff = abs(length_max - length_min)
            self._log(
                f"{prop_name}: Schnelltest → Länge_min {length_min}, Länge_max {length_max}, Unterschied {diff}"
            )
            # Wenn kein Unterschied festgestellt wird, überspringen wir die
            # weitere Kalibrierung dieses Parameters.  Die Baseline wird
            # dabei auf length_max gesetzt, da der ursprüngliche Wert
            # verwendet werden soll.
            if diff < 1:
                self._log(
                    f"{prop_name}: Kein relevanter Einfluss festgestellt → überspringe Kalibrierung"
                )
                baseline_length = length_max
                # Stelle sicher, dass der ursprüngliche Wert gesetzt bleibt
                setattr(scene, prop_name, original_value)
                # Baseline für nächste Schwelle aktualisieren
                # (bereits durch length_max gegeben).  Keine weitere
                # Kalibrierung nötig.
                continue

            # Unterschied festgestellt – Baseline auf length_max setzen und
            # Feintuning durchführen.
            baseline_length = length_max
            # Aktueller bester Wert (Startwert) und Länge
            best_value = original_value
            best_length = baseline_length
            self._log(
                f"Starte Tuning für {prop_name}: Ausgangswert {best_value:.6f}, Baseline {best_length}"
            )
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

                    _restore_selection()
                    reset_to_frame(context, start_frame)

                    self._log(f"[DEBUG] {prop_name} unmittelbar vor track_cycle(): {getattr(scene, prop_name)}")
                    try:
                        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    except Exception as e:
                        self._log(f"{prop_name} Fehler bei track_cycle in Stufe {step:+.2f}, Runde {iteration}:", e)
                        setattr(scene, prop_name, best_value)
                        break

                    self._log(f"[DEBUG] {prop_name} unmittelbar nach track_cycle(): {getattr(scene, prop_name)}")


                    sgn = get_total_track_length(context, start_frame)
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
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                self._log(f"[DEBUG] Baseline vor track_cycle für {prop_name}: {getattr(scene, prop_name)}")
                scene.update_tag()
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                self._log(f"[DEBUG] Baseline nach track_cycle für {prop_name}: {getattr(scene, prop_name)}")

            except Exception as e:
                self._log(f"Fehler beim track_cycle nach Beenden von {prop_name}:", e)
                return {'CANCELLED'}
            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        # Fertig: Playhead zurücksetzen und ursprüngliche Auswahl wiederherstellen
        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert‑Kalibrierung abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

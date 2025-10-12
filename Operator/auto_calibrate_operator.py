import bpy
from typing import List, Tuple

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

    # ---- CLIP_EDITOR Kontext finden (für detect_features/Delete) ----------------
    def _find_clip_editor_context(self, context) -> Tuple[object, object, object, object]:
        """Sucht eine gültige CLIP_EDITOR Area für Context-Override."""
        for window in bpy.context.window_manager.windows:
            screen = window.screen
            for area in screen.areas:
                if area.type != 'CLIP_EDITOR':
                    continue
                for space in area.spaces:
                    if getattr(space, "type", None) != 'CLIP_EDITOR':
                        continue
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    if region:
                        return window, area, region, space
        return None, None, None, None

    # ---- Ein Mess-Durchlauf: snapshot → detect → length → delete ----------------
    def _measure_with_detect_then_cleanup(self, context, start_frame: int) -> float:
        """
        Führt einen vollständigen Messzyklus aus:
        1) Snapshot aktiver Marker → set(old_names)
        2) Detect Features im gültigen CLIP_EDITOR-Kontext
        3) Messung der Gesamtlänge
        4) Löschen der neu hinzugekommenen Tracks anhand der Namen
        """
        space_data = getattr(context, "space_data", None)
        clip = getattr(space_data, "clip", None)
        if clip is None:
            self._log("Kein aktiver Clip für Messung.")
            return 0.0

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self._log("Clip hat kein tracking-Attribut.")
            return 0.0

        # 1) Snapshot (alte Marker/Tracks merken)
        old_names = set(snapshot_active_markers(context) or [])

        # 2) Detect Features (richtiger Kontext)
        win, area, region, space = self._find_clip_editor_context(context)
        if all((win, area, region, space)):
            override = {'window': win, 'area': area, 'region': region, 'space_data': space}
            try:
                # detect_features: Helper, der intern bpy.ops.clip.detect_features korrekt nutzt
                detect_features(context=override if 'space_data' in override else context)
            except Exception as e:
                self._log("detect_features fehlgeschlagen:", e)
        else:
            # Fallback: versuche ohne Override
            try:
                detect_features(context=context)
            except Exception as e:
                self._log("detect_features ohne Override fehlgeschlagen:", e)

        # 3) Gesamtlänge messen (Playhead vorher zurücksetzen)
        reset_to_frame(context, start_frame)
        segment_length = get_total_track_length(context, start_frame)

        # 4) Neu entstandene Track-Namen bestimmen und löschen
        try:
            current_names = [t.name for t in tracking.tracks]
            new_names = [n for n in current_names if n not in old_names]
            if new_names:
                delete_tracks_by_names(context, new_names)
        except Exception as e:
            self._log("Löschen der neuen Tracks fehlgeschlagen:", e)

        return float(segment_length)    # Liste der Schwellenwerte (Property‑Namen) in der Reihenfolge der Tuning‑Reihenfolge.
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

        # Entfernt: "selected Marker Schranke" und Selektions-Wiederherstellung.
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

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

        # Erste Baseline: detect → messen → delete (keine track_cycle-Nutzung mehr)
        reset_to_frame(context, start_frame)
        scene.update_tag()
        baseline_length = self._measure_with_detect_then_cleanup(context, start_frame)
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
            try:
                scene.update_tag()
                length_min = self._measure_with_detect_then_cleanup(context, start_frame)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (min) für {prop_name}:", e)
                setattr(scene, prop_name, original_value)
                continue
            
            # Test mit ursprünglichem (maximalem) Schwellenwert
            setattr(scene, prop_name, original_value)
            
            reset_to_frame(context, start_frame)
            try:
                scene.update_tag()
                length_max = self._measure_with_detect_then_cleanup(context, start_frame)
            except Exception as e:
                self._log(f"Fehler beim Schnelltest (max) für {prop_name}:", e)
                continue
            
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

                    # detect → measure → delete
                    try:
                        sgn = self._measure_with_detect_then_cleanup(context, start_frame)
                    except Exception as e:
                        self._log(f"{prop_name} Fehler im Messzyklus Stufe {step:+.2f}, Runde {iteration}:", e)
                        setattr(scene, prop_name, best_value)
                        break

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
            try:
                self._log(f"[DEBUG] Baseline vor track_cycle für {prop_name}: {getattr(scene, prop_name)}")
                baseline_length = self._measure_with_detect_then_cleanup(context, start_frame)
                self._log(f"[DEBUG] Baseline nach Messzyklus für {prop_name}: {getattr(scene, prop_name)}")

            except Exception as e:
                self._log(f"Fehler beim Messzyklus nach Beenden von {prop_name}:", e)
                return {'CANCELLED'}
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value}, neue Baseline {baseline_length}")

        # Fertig: Playhead zurücksetzen
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

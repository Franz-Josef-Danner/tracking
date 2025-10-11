"""
auto_calibrate_operator
=======================

This operator implements an automated calibration routine for the
threshold sliders exposed in the Kaiserlich Tracker UI.  It performs
multiple tracking cycles using the existing ``track_cycle`` operator and
measures the combined length of all selected markers.  For each
threshold parameter the operator progressively reduces its value by five
percent and observes whether the total tracked length increases,
decreases or remains unchanged.  As soon as a reduction fails to
improve the result (or yields the same result four times in a row),
the previous best value is retained and the operator moves on to the
next parameter.  When complete the thresholds in the scene reflect
values that maximise the length of the tracking results for the
currently selected markers.

The operator is intentionally blocking; it runs a potentially large
number of tracking cycles in sequence.  If your clip is long or you
have many markers, calibration may take a noticeable amount of time.

Usage
-----
Register the operator and add it to the UI (for example as a button in
``ui.py``).  When invoked it will reset all threshold sliders to 1.0,
run an initial track cycle to establish a baseline and then tune each
threshold in the following order:

    1. ``kaiserlich_rot_thresh_x``
    2. ``kaiserlich_rot_thresh_y``
    3. ``kaiserlich_scale_thresh_min``
    4. ``kaiserlich_scale_thresh_max``
    5. ``kaiserlich_rot_scale_thresh_rot``
    6. ``kaiserlich_rot_scale_thresh_scale``
    7. ``kaiserlich_perspective_thresh``

Each parameter is multiplied by 0.95 in successive iterations until
reducing it further no longer improves the total tracked length.
"""

from __future__ import annotations

import bpy

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung der Bewegungsmodell-Schwellenwerte.

    Diese Operator-Klasse durchläuft alle in der UI definierten
    Schwellenwerte für Rotations‑, Skalierungs‑, kombinierten
    Rotations/Skalierungs‑ und Perspektiv‑Erkennung.  Ausgehend von
    einem Startwert von 1.0 pro Schwellwert wird der Tracking‑Zyklus
    wiederholt und der Gesamtumfang der getrackten Segmente summiert.
    Der Schwellwert wird so lange um 5 % reduziert, bis der gefundene
    Gesamtumfang nicht länger steigt (oder viermal hintereinander
    unverändert bleibt).  Der beste gefundene Wert wird beibehalten.
    """

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
            # Aktueller bester Wert und Länge
            best_value = getattr(scene, prop_name)
            best_length = baseline_length
            # Log start of tuning for this property
            self._log(
                f"Starte Tuning für {prop_name}: Ausgangswert {best_value:.6f}, Baseline {best_length}"
            )
            iteration = 0
            while True:
                iteration += 1
                # Berechne neuen Wert (5‑% Reduktion)
                current_value = getattr(scene, prop_name)
                new_value = current_value * 0.95
                # Vermeide negative oder zu kleine Werte.  Wenn die
                # Untergrenze erreicht wird, brechen wir die Kalibrierung für
                # diesen Parameter ab und kehren auf den besten Wert zurück.
                if new_value <= self.MIN_THRESHOLD:
                    # Setze den bestmöglichen gefundenen Wert (oder lasse den
                    # Wert unverändert, falls noch keine Verbesserung gefunden
                    # wurde) und beende das Tuning dieser Property.
                    setattr(scene, prop_name, best_value)
                    self._log(
                        f"{prop_name}: Untergrenze {self.MIN_THRESHOLD:.5f} erreicht → zurücksetzen auf {best_value:.6f} und weiterspringen"
                    )
                    break
                # Ansonsten schreibe den neuen Schwellenwert und fahre fort
                setattr(scene, prop_name, new_value)
                self._log(f"{prop_name} Runde {iteration}: teste Wert {new_value:.6f}")

                # Tracking ausführen
                _restore_selection()
                reset_to_frame(context, start_frame)
                try:
                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                except Exception as e:
                    self._log(f"Fehler beim track_cycle in {prop_name} Runde {iteration}:", e)
                    # Im Fehlerfall beenden und den besten Wert beibehalten
                    setattr(scene, prop_name, best_value)
                    break
                new_length = get_total_track_length(context, start_frame)
                self._log(f"{prop_name} Runde {iteration}: Länge {new_length}")

                # Wenn das Ergebnis nicht schlechter ist als das bislang beste, fahre fort.
                # Gleichbleibende Länge wird nicht mehr als Abbruchbedingung genutzt.
                if new_length >= best_length:
                    if new_length > best_length:
                        # Verbesserung gefunden
                        best_length = new_length
                        best_value = new_value
                        self._log(f"{prop_name}: Verbesserung → Wert {new_value:.6f}, Länge {new_length}")
                    else:
                        # Keine Veränderung – fahre mit weiterer Reduktion fort
                        self._log(f"{prop_name}: keine Veränderung (gleichbleibend)")
                    # Mit dem nächsten Iterationsschritt fortfahren
                    continue
                else:
                    # Verschlechterung → letzten guten Wert zurücksetzen und abbrechen
                    setattr(scene, prop_name, best_value)
                    self._log(f"{prop_name}: Verschlechterung (Länge {new_length} < {best_length}) → zurücksetzen auf {best_value}")
                    break
            # Nach Abschluss des Loops: sichergehen, dass der beste Wert gesetzt ist
            setattr(scene, prop_name, best_value)
            # Baseline für nächste Schwelle aktualisieren: Führe Tracking erneut aus
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
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

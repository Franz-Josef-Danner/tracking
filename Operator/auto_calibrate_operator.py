import bpy
from typing import List

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import detect_features
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Schwellenwert-Kalibrierung über stufenweise Variation und Segmentlängen-Evaluierung."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = (
        "Kalibriert automatisch die Schwellenwerte für die Bewegungsmodelle "
        "durch wiederholtes Tracking und Längenmessung."
    )
    bl_options = {"REGISTER", "UNDO"}

    # -----------------------------
    # Properties
    # -----------------------------
    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole während der Kalibrierung",
    )

    # Grenzwerte für Threshold-Parameter
    MIN_THRESHOLD: float = 1e-8
    MAX_THRESHOLD: float = 1.0

    # Zu kalibrierende Properties (müssen in Scene existieren)
    _threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

    # Stufenfolge (fix im Code)
    _steps = [-0.95, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]

    # -----------------------------
    # Utils
    # -----------------------------
    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def _detect_track_length(self, context, start_frame: int) -> int:
        """Snapshot → Detect → Track → Length → Delete (nur neu erzeugte Tracks löschen)."""
        clip = context.space_data.clip
        tracking = clip.tracking

        old_track_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        detect_features(context)

        # neu erzeugte Tracks identifizieren
        new_track_names = [t.name for t in tracking.tracks if t.name not in old_track_names]

        # nur neue selektieren (Track-Operator arbeitet typischerweise über Selektion)
        for tr in tracking.tracks:
            tr.select = (tr.name in new_track_names)

        # Tracken
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)

        # Länge messen
        length = get_total_track_length(context, start_frame)

        # neue wieder löschen
        delete_tracks_by_names(context, new_track_names)

        return length

    def _set_prop(self, scene, prop_name: str, value: float) -> float:
        """Wert mit Klammerung setzen und rückrunden, gibt den tatsächlich gesetzten Wert zurück."""
        v = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(value)))
        setattr(scene, prop_name, self._round(v))
        scene.update_tag()
        return getattr(scene, prop_name)

    # -----------------------------
    # Execute
    # -----------------------------
    def execute(self, context: bpy.types.Context):
        # Vorbedingungen
        if getattr(context, "space_data", None) is None or getattr(context.space_data, "clip", None) is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        clip = context.space_data.clip
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking-Attribut.")
            return {'CANCELLED'}

        # Auswahl sichern & deselektieren (wir arbeiten nur mit neuen Tracks je Messung)
        selected_names: List[str] = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        # Startframe ermitteln
        start_frame = get_start_frame(context)
        self._log(f"Startframe erfasst: {start_frame}")

        # Alle zu kalibrierenden Properties initial auf 1.0 setzen (neutral)
        for prop_name in self._threshold_props:
            if hasattr(context.scene, prop_name):
                self._set_prop(context.scene, prop_name, 1.0)
            else:
                self._log(f"Warnung: Property '{prop_name}' existiert nicht auf der Szene.")

        # Globale Baseline mit Threshold=1.0 (für den Clip insgesamt, Info/Monitoring)
        reset_to_frame(context, start_frame)
        baseline_length = self._detect_track_length(context, start_frame)
        self._log(f"Baseline Länge (global, 1.0): {baseline_length}")

        # ------------------------------------------
        # Pro Property: Kurztest und stufenbasierter Haupttest
        # ------------------------------------------
        for prop_name in self._threshold_props:
            if not hasattr(context.scene, prop_name):
                self._log(f"{prop_name}: Übersprungen (Property fehlt).")
                continue

            # -----------------------------
            # KURZTEST – prüft, ob Kalibrierung sinnvoll ist
            # -----------------------------
            self._log(f"{prop_name}: Starte Kurztest (MIN vs. 1.0)")

            reset_to_frame(context, start_frame)
            self._set_prop(context.scene, prop_name, self.MIN_THRESHOLD)
            length_min = self._detect_track_length(context, start_frame)

            reset_to_frame(context, start_frame)
            self._set_prop(context.scene, prop_name, 1.0)
            length_neutral = self._detect_track_length(context, start_frame)

            self._log(f"{prop_name}: Kurztest → Länge_min={length_min:.2f}, Länge_1.0={length_neutral:.2f}")

            if length_min <= length_neutral:
                self._log(f"{prop_name}: Kein positiver Einfluss → Haupttest übersprungen.")
                continue

            # -----------------------------
            # HAUPTTEST
            # Baseline beibehalten, aber stufenübergreifend sofortige Änderungsdetektion:
            # sg_prev wird über Stufen hinweg fortgeschrieben.
            # -----------------------------
            self._log(f"{prop_name}: Starte Haupttest")
            reset_to_frame(context, start_frame)
            self._set_prop(context.scene, prop_name, 1.0)

            # Baseline speziell für dieses Property messen
            base_length = self._detect_track_length(context, start_frame)
            sg_prev = base_length  # stufenübergreifender Vergleichswert
            current_value = 1.0

            self._log(f"{prop_name}: Haupttest-Basis gesetzt → Länge {base_length:.2f}")

            # Flags über Stufen hinweg führen (für klareres Verhalten)
            improved_any = False  # hat es in irgendeiner Stufe bereits eine Verbesserung gegeben?

            for step in self._steps:
                iteration = 0
                stagnation_count = 0
                self._log(f"{prop_name}: Starte Stufe {step:+.2f} (Startwert={current_value:.8f}, sg_prev={sg_prev})")

                while True:
                    iteration += 1

                    # Nächster Kandidat
                    new_value = self._round(current_value * (1.0 + step), 8)
                    if new_value <= self.MIN_THRESHOLD:
                        self._log(f"{prop_name}: Untergrenze erreicht ({new_value:.8f}) → Stufe beendet")
                        break
                    if new_value >= self.MAX_THRESHOLD:
                        self._log(f"{prop_name}: Obergrenze erreicht ({new_value:.8f}) → Stufe beendet")
                        break

                    # Setzen & messen
                    self._set_prop(context.scene, prop_name, new_value)
                    reset_to_frame(context, start_frame)
                    sgn = self._detect_track_length(context, start_frame)

                    self._log(
                        f"{prop_name} Stufe {step:+.2f} "
                        f"Iter {iteration:02d}: Wert {new_value:.8f} → Segmentlänge {sgn} (sg_prev={sg_prev})"
                    )

                    # ---- Bewertungslogik mit stufenübergreifendem sg_prev ----
                    if sgn > sg_prev:
                        # Verbesserung
                        improved_any = True
                        sg_prev = sgn
                        stagnation_count = 0
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                        current_value = new_value
                        # weiter iterieren (Feintuning), keine Blinditeration nötig
                        continue

                    if sgn == sg_prev:
                        # Stagnation
                        stagnation_count += 1
                        current_value = new_value
                        if stagnation_count >= 2:
                            self._log(f"{prop_name}: Stagnation (2x) → Stufe beendet")
                            break
                        # Einmalige Stagnation → noch einmal versuchen
                        continue

                    # sgn < sg_prev → Verschlechterung
                    self._log(f"{prop_name}: Verschlechterung erkannt → Stufe beendet")
                    # current_value trotzdem fortschreiben, um den Pfad fortzusetzen
                    current_value = new_value
                    break

                # Wichtiger Punkt:
                # sg_prev bleibt der führende Vergleichswert und wird NICHT künstlich zurückgesetzt.
                # Dadurch erkennt die nächste Stufe bereits im ersten Durchlauf echte Änderungen.

            # Abschlussmessung mit finalem Wert aus dem Haupttest
            reset_to_frame(context, start_frame)
            self._set_prop(context.scene, prop_name, current_value)
            final_length = self._detect_track_length(context, start_frame)

            self._log(
                f"{prop_name}: Haupttest abgeschlossen – finaler Wert {current_value:.8f}, "
                f"Abschlusslänge {final_length:.2f} (Baseline {base_length:.2f})"
            )

        # Aufräumen & Restore
        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Schwellenwert-Kalibrierung abgeschlossen.")
        self._log("Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

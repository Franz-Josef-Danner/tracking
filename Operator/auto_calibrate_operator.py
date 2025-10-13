import bpy
from typing import List

from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.detect import detect_features
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from .Operator.track_operator import KAISERLICHTRACKER_OT_track_cycle

class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kalibriert automatisch die Schwellenwerte für Bewegungsmodelle
    durch mehrstufige, adaptive Wiederholung mit Veränderungs- und Feintuning-Phase."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Führt stufenweise Threshold-Kalibrierung mit dynamischer Verbesserungssuche durch."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging während der Kalibrierung",
    )

    MIN_THRESHOLD: float = 1e-8
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

    _steps = [-0.95, +0.95, -0.20, +0.20, -0.05, +0.05, -0.01]

    # ---------------------------------------
    # Hilfsfunktionen
    # ---------------------------------------
    def _round(self, value: float, decimals: int = 8) -> float:
        return round(value, decimals)

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate]", *msg)

    def _detect_track_length(self, context, start_frame: int) -> int:
        """Snapshot → Detect → Track → Length → Delete."""
        clip = context.space_data.clip
        tracking = clip.tracking

        old_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        KAISERLICHTRACKER_OT_track_cycle(context)

        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        for tr in tracking.tracks:
            tr.select = tr.name in new_names

        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        length = get_total_track_length(context, start_frame)
        delete_tracks_by_names(context, new_names)

        return length

    def _set_prop(self, scene, prop_name: str, value: float) -> float:
        v = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(value)))
        setattr(scene, prop_name, self._round(v))
        scene.update_tag()
        return getattr(scene, prop_name)

    # ---------------------------------------
    # Hauptausführung
    # ---------------------------------------
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

        selected_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)
        self._log(f"Startframe: {start_frame}")

        # Init aller Properties
        for p in self._threshold_props:
            if hasattr(scene, p):
                self._set_prop(scene, p, 1.0)

        # Globale Baseline
        reset_to_frame(context, start_frame)
        baseline_length = self._detect_track_length(context, start_frame)
        self._log(f"Globale Baseline Länge: {baseline_length}")

        # ==================================================
        # HAUPTSCHLEIFE pro Property
        # ==================================================
        for prop_name in self._threshold_props:
            if not hasattr(scene, prop_name):
                continue

            # ---------- Kurztest ----------
            self._log(f"{prop_name}: Starte Kurztest (MIN vs 1.0)")
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, self.MIN_THRESHOLD)
            length_min = self._detect_track_length(context, start_frame)

            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, 1.0)
            length_neutral = self._detect_track_length(context, start_frame)

            self._log(f"{prop_name}: Kurztest → min={length_min}, neutral={length_neutral}")
            if length_min <= length_neutral:
                self._log(f"{prop_name}: Kein signifikanter Unterschied – überspringe Haupttest.")
                continue

            # ---------- Haupttest ----------
            self._log(f"{prop_name}: Starte Haupttest …")

            # Baseline
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, 1.0)
            sg_prev = self._detect_track_length(context, start_frame)
            current_value = 1.0
            self._log(f"{prop_name}: Baseline gesetzt → Länge {sg_prev}")

            for step in self._steps:
                iteration = 0
                change_detected = False
                stagnation_count = 0
                self._log(f"{prop_name}: Stufe {step:+.2f} startet (Startwert {current_value:.8f})")

                while True:
                    iteration += 1
                    new_value = self._round(current_value * (1.0 + step), 8)
                    if new_value <= self.MIN_THRESHOLD or new_value >= self.MAX_THRESHOLD:
                        self._log(f"{prop_name}: Wert {new_value:.8f} außerhalb der Grenzen → Abbruch Stufe.")
                        break

                    self._set_prop(scene, prop_name, new_value)
                    reset_to_frame(context, start_frame)
                    sgn = self._detect_track_length(context, start_frame)

                    self._log(
                        f"{prop_name}: Stufe {step:+.2f} Iter {iteration:02d} → Wert {new_value:.8f}, "
                        f"Länge {sgn}, Prev {sg_prev}"
                    )

                    # === 1. Zyklus: Veränderungssuche ===
                    if not change_detected:
                        if sgn != sg_prev:
                            change_detected = True
                            if sgn > sg_prev:
                                self._log(f"{prop_name}: Verbesserung erkannt → Wechsel in Feintuning.")
                                sg_prev = sgn
                                current_value = new_value
                                continue
                            else:
                                self._log(f"{prop_name}: Verschlechterung bei erster Änderung → Stufe beendet.")
                                current_value = new_value
                                break
                        else:
                            current_value = new_value
                            continue  # weiter suchen

                    # === 2. Zyklus: Feintuning ===
                    if sgn > sg_prev:
                        self._log(f"{prop_name}: Verbesserung → Länge {sgn}")
                        sg_prev = sgn
                        stagnation_count = 0
                        current_value = new_value
                        continue

                    elif sgn == sg_prev:
                        stagnation_count += 1
                        current_value = new_value
                        if stagnation_count >= 1:
                            self._log(f"{prop_name}: Stagnation erkannt → Stufe beendet.")
                            break
                        else:
                            continue

                    else:  # sgn < sg_prev
                        self._log(f"{prop_name}: Verschlechterung erkannt → Stufe beendet.")
                        current_value = new_value
                        break

                sg_prev = sgn  # ← letzter Messwert, auch wenn schlechter als vorheriger Bestwert

            # ---------- Abschlussmessung ----------
            reset_to_frame(context, start_frame)
            self._set_prop(scene, prop_name, current_value)
            final_length = self._detect_track_length(context, start_frame)
            self._log(
                f"{prop_name}: Haupttest abgeschlossen – Finalwert {current_value:.8f}, "
                f"Länge {final_length} (Baseline {baseline_length})"
            )

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        self._log("Auto-Calibrate vollständig abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

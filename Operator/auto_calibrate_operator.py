
from __future__ import annotations

import bpy
from typing import List, Tuple, Callable

# Assumed helpers (adjust imports to your package layout)
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


STEPS: List[float] = [
    0.10,   # st=1 → -90%  → multiply by 0.10
    1.50,   # st=2 → +50%  → multiply by 1.50
    0.75,   # st=3 → -25%  → multiply by 0.75
    1.10,   # st=4 → +10%  → multiply by 1.10
    0.95,   # st=5 → -5%   → multiply by 0.95
    1.02,   # st=6 → +2%   → multiply by 1.02
    0.99,   # st=7 → -1%   → multiply by 0.99
]


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Auto‑Calibrate per explicit staged multipliers.

    Kernlogik (pro Threshold-Parameter):
        - sg := Segmentlängen‑Summe nach einem Referenz‑Cycle (cyclus 1)
        - Für jede Stufe st in STEPS:
            * Setze th := th * st (ohne Reset zwischendurch)
            * Führe cyclus 1 aus → sgn := neue Segmentlängen‑Summe
            * Wenn sgn == sg → weiter zur nächsten Stufe (keine Änderung)
            * Wenn sgn  > sg → betrete cyclus 2:
                - Führe erneut track_cycle aus
                - Wenn neue Länge <= vorheriger sg → "threshold wechsel" (Rollback auf vorher bestes th) und zurück zu cyclus 1
                - Sonst bleibe in cyclus 2 (besser), setze sg := sgn, und gehe zur nächsten Stufe
            * Wenn sgn  < sg → Verschlechterung → Rollback auf vorher bestes th, zur nächsten Stufe
        - Der über alle Stufen beste Wert bleibt gesetzt.
        - Während der Zyklen erfolgt KEIN Reset der Threshold‑Properties – nur Multiplikation gemäß STEPS.
    """

    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto‑Calibrate (Staged)"
    bl_description = "Kalibriert Schwellenwerte mit festen Stufen: -90%, +50%, -25%, +10%, -5%, +2%, -1%"
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging der Stufenlogik",
    )

    # Reihenfolge der zu optimierenden Scene-Properties (anpassen an UI)
    threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

    MIN_VALUE: float = 1e-8
    MAX_VALUE: float = 1e+6

    def _log(self, *msg) -> None:
        if self.verbose:
            print("[Kaiserlich Tracker][AutoCalibrate Staged]", *msg)

    def _safe_mul(self, val: float, mul: float) -> float:
        out = val * mul
        if out < self.MIN_VALUE:
            out = self.MIN_VALUE
        if out > self.MAX_VALUE:
            out = self.MAX_VALUE
        return out

    def _run_cycle_and_measure(self, context: bpy.types.Context, start_frame: int) -> float:
        # cyclus 1 / 2 wird über denselben Operator gefahren
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        return get_total_track_length(context, start_frame)

    def execute(self, context: bpy.types.Context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip Editor.")
            return {'CANCELLED'}

        tracking = getattr(clip, "tracking", None)
        if tracking is None or not tracking.tracks:
            self.report({'WARNING'}, "Keine Tracking-Daten im Clip gefunden.")
            return {'CANCELLED'}

        # Merke Auswahl
        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Tracks gefunden.")
            return {'CANCELLED'}

        def restore_selection():
            for tr in tracking.tracks:
                tr.select = (tr.name in selected_names)

        start_frame = get_start_frame(context)
        self._log(f"Startframe: {start_frame}")

        # Baseline vor Start jeder Property
        restore_selection()
        reset_to_frame(context, start_frame)
        try:
            baseline_len_global = self._run_cycle_and_measure(context, start_frame)
        except Exception as e:
            self._log("Fehler beim initialen track_cycle:", e)
            return {'CANCELLED'}
        self._log(f"Global Baseline: {baseline_len_global}")

        # === Hauptschleife über alle Threshold-Properties ===
        for prop in self.threshold_props:
            if not hasattr(context.scene, prop):
                self._log(f"Überspringe unbekannte Property: {prop}")
                continue

            th_current = float(getattr(context.scene, prop))
            best_value = th_current
            restore_selection()
            reset_to_frame(context, start_frame)

            # sg: Referenzlänge (cyclus 1) unter aktuellem th
            try:
                sg = self._run_cycle_and_measure(context, start_frame)
            except Exception as e:
                self._log(f"{prop}: Fehler beim Referenz‑Cycle:", e)
                continue
            best_length = sg
            self._log(f"{prop}: Start th={th_current:.6f}, sg={sg}")

            # Stufenverarbeitung
            for idx, mul in enumerate(STEPS, start=1):
                restore_selection()
                reset_to_frame(context, start_frame)

                # th := th * st  (ohne Reset)
                prev_th = float(getattr(context.scene, prop))
                th_new = self._safe_mul(prev_th, mul)
                setattr(context.scene, prop, th_new)
                self._log(f"{prop}: st={idx}, mul={mul}, th: {prev_th:.6f} → {th_new:.6f}")

                # cyclus 1 → sgn
                try:
                    sgn = self._run_cycle_and_measure(context, start_frame)
                except Exception as e:
                    self._log(f"{prop}: Fehler in cyclus 1 (st={idx}):", e)
                    # Rollback auf previous best
                    setattr(context.scene, prop, best_value)
                    continue

                self._log(f"{prop}: st={idx}, cyclus1 sgn={sgn} (sg={sg})")

                if sgn == sg:
                    # Keine Veränderung → nächste Stufe
                    self._log(f"{prop}: st={idx}, keine Veränderung → weiter")
                    continue

                if sgn > sg:
                    # Verbesserung → cyclus 2 prüfen
                    self._log(f"{prop}: st={idx}, Verbesserung → cyclus 2")
                    restore_selection()
                    reset_to_frame(context, start_frame)
                    try:
                        sgn2 = self._run_cycle_and_measure(context, start_frame)
                    except Exception as e:
                        self._log(f"{prop}: Fehler in cyclus 2 (st={idx}):", e)
                        # Rollback auf previous best
                        setattr(context.scene, prop, best_value)
                        continue

                    self._log(f"{prop}: st={idx}, cyclus2 sgn2={sgn2}, vorher sg={sg}")

                    if sgn2 <= sg:
                        # threshold wechsel → Rollback
                        setattr(context.scene, prop, best_value)
                        self._log(f"{prop}: st={idx}, threshold wechsel → Rollback auf {best_value:.6f}")
                        # zurück zu cyclus 1 mit altem sg (kein Reset nötig)
                        continue
                    else:
                        # Verbesserung bestätigt → übernehmen
                        sg = sgn2
                        if sg > best_length:
                            best_length = sg
                            best_value = float(getattr(context.scene, prop))
                            self._log(f"{prop}: st={idx}, neuer Bestwert th={best_value:.6f}, len={best_length}")
                        continue

                # sgn < sg → Verschlechterung → Rollback und weiter
                setattr(context.scene, prop, best_value)
                self._log(f"{prop}: st={idx}, Verschlechterung → Rollback auf th={best_value:.6f}")

            # Nach allen Stufen sicherstellen, dass bester Wert gesetzt bleibt
            setattr(context.scene, prop, best_value)
            self._log(f"{prop}: abgeschlossen, bester th={best_value:.6f}, best_len={best_length}")

            # Optionale Aktualisierung der globalen Baseline
            restore_selection()
            reset_to_frame(context, start_frame)
            try:
                baseline_len_global = self._run_cycle_and_measure(context, start_frame)
                self._log(f"{prop}: neue globale Baseline nach Abschluss: {baseline_len_global}")
            except Exception as e:
                self._log(f"{prop}: Fehler bei Baseline‑Aktualisierung:", e)

        reset_to_frame(context, start_frame)
        restore_selection()
        self.report({'INFO'}, "Auto‑Calibrate (Staged) abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

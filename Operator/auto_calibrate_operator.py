
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


@@ class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
             # Unterschied festgestellt – Baseline auf length_max setzen und
             # Feintuning durchführen.
             baseline_length = length_max
             # Aktueller bester Wert (Startwert) und Länge
             best_value = original_value
             best_length = baseline_length
             self._log(
                 f"Starte Tuning für {prop_name}: Ausgangswert {best_value:.6f}, Baseline {best_length}"
             )
            # =============================================================
            # Hauptprüfung in 7 Stufen (Threshold wird von Stufe zu Stufe weitergereicht)
            # =============================================================
            stages = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]

            # Ausgangswerte
            current_value = best_value
            sg = best_length  # Ausgangssegmentlänge

            for idx, s in enumerate(stages, start=1):
                factor = 1.0 + s
                th_new = current_value * factor

                # Sicherheitsgrenze prüfen
                if th_new <= self.MIN_THRESHOLD:
                    self._log(f"{prop_name}: Stufe {idx} ({s:+.0%}) → Untergrenze erreicht ({th_new:.6f}), Abbruch.")
                    break

                setattr(scene, prop_name, th_new)
                _restore_selection()
                reset_to_frame(context, start_frame)

                try:
                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                except Exception as e:
                    self._log(f"{prop_name}: Fehler in Stufe {idx} ({s:+.0%}):", e)
                    continue

                sgn = get_total_track_length(context, start_frame)

                # Vergleich alt vs neu
                if sgn > sg:
                    self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) → Verbesserung ({sgn:.2f} > {sg:.2f}) → neuer Wert {th_new:.6f}")
                    sg = sgn
                    current_value = th_new
                    best_value = th_new
                    best_length = sgn
                elif sgn == sg:
                    self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) → keine Veränderung ({sgn:.2f} == {sg:.2f})")
                    # optional Wiederholung derselben Stufe wäre hier möglich
                else:
                    self._log(f"{prop_name}: Stage {idx} ({s:+.0%}) → Verschlechterung ({sgn:.2f} < {sg:.2f}) → weiter zur nächsten Stufe")
                    # keine Rücksetzung – einfach fortsetzen
                    continue

            # Nach Abschluss aller Stufen: bester Wert fixieren
            setattr(scene, prop_name, best_value)

            # Neue Baseline für nächste Schwelle berechnen
            _restore_selection()
            reset_to_frame(context, start_frame)
            try:
                bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            except Exception as e:
                self._log(f"Fehler beim track_cycle nach Abschluss von {prop_name}:", e)
                return {'CANCELLED'}
            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"{prop_name}: Fertig. Bester Wert {best_value:.6f}, neue Baseline {baseline_length:.2f}")

        reset_to_frame(context, start_frame)
        _restore_selection()
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()

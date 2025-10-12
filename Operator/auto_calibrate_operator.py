
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
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Führt eine automatische Schwellenwert-Kalibrierung durch"
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(default=True)

    _threshold_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    ]

    _steps = [-0.90, +0.50, -0.25, +0.10, -0.05, +0.02, -0.01]
    MIN_THRESHOLD = 1e-5

    def _log(self, *msg):
        if self.verbose:
            print("[AutoCalibrate]", *msg)

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip aktiv.")
            return {'CANCELLED'}
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            self.report({'WARNING'}, "Kein Tracking im Clip.")
            return {'CANCELLED'}

        selected_names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
        if not selected_names:
            self.report({'WARNING'}, "Keine selektierten Marker.")
            return {'CANCELLED'}

        def _restore_selection():
            for tr in tracking.tracks:
                tr.select = tr.name in selected_names

        start_frame = get_start_frame(context)

        # --- Baseline vorbereiten ---
        _restore_selection()
        reset_to_frame(context, start_frame)
        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        baseline_length = get_total_track_length(context, start_frame)
        self._log(f"Initiale Baseline: {baseline_length}")

        # --- Kalibrierung pro Parameter ---
        for prop in self._threshold_props:
            if not hasattr(scene, prop):
                self._log(f"Überspringe fehlendes Property: {prop}")
                continue

            th_val = getattr(scene, prop)
            best_val, best_len = th_val, baseline_length
            self._log(f"Start Kalibrierung: {prop} = {th_val}")

            for st_i, st_change in enumerate(self._steps, 1):
                improved = False
                stagnation_count = 0
                self._log(f"[{prop}] Stufe {st_i}: {st_change:+.2%}")

                while True:
                    # neuen Threshold berechnen
                    new_val = th_val * (1.0 + st_change)
                    if new_val <= self.MIN_THRESHOLD:
                        self._log(f"{prop}: Mindestwert erreicht → Abbruch Stufe.")
                        break

                    setattr(scene, prop, new_val)
                    _restore_selection()
                    reset_to_frame(context, start_frame)
                    bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
                    new_len = get_total_track_length(context, start_frame)
                    self._log(f"{prop}: Test={new_val:.6f}, Länge={new_len}")

                    if new_len > best_len:
                        self._log(f"{prop}: Verbesserung ({new_len} > {best_len})")
                        best_len = new_len
                        best_val = new_val
                        th_val = new_val
                        improved = True
                        stagnation_count = 0
                        continue
                    elif new_len == best_len:
                        stagnation_count += 1
                        if stagnation_count >= 2:
                            self._log(f"{prop}: Stagnation → nächste Stufe")
                            break
                        else:
                            continue
                    else:
                        self._log(f"{prop}: Verschlechterung → nächste Stufe")
                        break

                # nach jeder Stufe aktuellen besten Wert setzen
                setattr(scene, prop, best_val)
                th_val = best_val

            # finalen Wert übernehmen und Baseline updaten
            setattr(scene, prop, best_val)
            _restore_selection()
            reset_to_frame(context, start_frame)
            bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
            baseline_length = get_total_track_length(context, start_frame)
            self._log(f"{prop}: Finaler Wert {best_val:.6f}, neue Baseline={baseline_length}")

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

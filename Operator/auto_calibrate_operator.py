import bpy
from typing import Tuple
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Threshold-Kalibrierung mit einseitiger Downward-Search und Gate-Mechanismus."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Einseitige Downward-Search mit Zielwertsteuerung und Gate-Logik."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Detailliertes Logging während der Kalibrierung"
    )

    MIN_THRESHOLD: float = 1e-8
    MAX_THRESHOLD: float = 1.0

    _single_props = [
        "kaiserlich_rot_thresh_x",
        "kaiserlich_perspective_thresh",
    ]

    _pair_props = [
        ("kaiserlich_scale_thresh_min", "kaiserlich_scale_thresh_max"),
        ("kaiserlich_rot_scale_thresh_rot", "kaiserlich_rot_scale_thresh_scale"),
    ]

    _down_steps = [0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
    _next_start: dict = {}

    # ----------------------------------------------------
    # Utilities
    # ----------------------------------------------------
    def _round(self, v: float, decimals: int = 8) -> float:
        return round(float(v), decimals)

    def _clip_set(self, scene, prop: str, value: float) -> float:
        v = max(self.MIN_THRESHOLD, min(self.MAX_THRESHOLD, float(value)))
        setattr(scene, prop, self._round(v))
        scene.update_tag()
        return getattr(scene, prop)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    # ----------------------------------------------------
    # Track-Längenmessung
    # ----------------------------------------------------
    def _detect_track_length(self, context, start_frame: int) -> int:
        clip = context.space_data.clip
        tracking = clip.tracking
        old_names = [t.name for t in tracking.tracks]
        snapshot_active_markers(context)
        bpy.ops.kaiserlich_tracker.detect_adapt()

        new_names = [t.name for t in tracking.tracks if t.name not in old_names]
        for tr in tracking.tracks:
            tr.select = (tr.name in new_names)

        bpy.ops.kaiserlich_tracker.track_cycle(max_frames=0, verbose=False)
        length = get_total_track_length(context, start_frame)
        delete_tracks_by_names(context, new_names)
        return length

    # ----------------------------------------------------
    # Kurztest (Einzel)
    # ----------------------------------------------------
    def _short_test_single(self, context, start_frame: int, prop: str) -> Tuple[bool, int]:
        scene = context.scene
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop, 1.0)
        length_neutral = self._detect_track_length(context, start_frame)

        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop, self.MIN_THRESHOLD)
        length_min = self._detect_track_length(context, start_frame)

        return (length_min > length_neutral), max(length_min, length_neutral)

    # ----------------------------------------------------
    # Kurztest (Paar)
    # ----------------------------------------------------
    def _short_test_pair(self, context, start_frame: int, prop_a: str, prop_b: str) -> Tuple[bool, int]:
        scene = context.scene
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, 1.0)
        self._clip_set(scene, prop_b, 1.0)
        length_neutral = self._detect_track_length(context, start_frame)

        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, self.MIN_THRESHOLD)
        self._clip_set(scene, prop_b, self.MIN_THRESHOLD)
        length_min = self._detect_track_length(context, start_frame)

        return (length_min > length_neutral), max(length_min, length_neutral)

    # ----------------------------------------------------
    # Haupttest (Einzel) - mit Gate
    # ----------------------------------------------------
    def _downward_search_single(self, context, start_frame: int, prop: str, target_length: int, start_value: float = 1.0):
        scene = context.scene
        current = start_value
        prev_value = current
        best_length = -1
        new_min = self.MIN_THRESHOLD
        new_start = start_value

        self._log(f"[AutoCalib][{prop}] start={start_value:.6f}")

        for f in self._down_steps:
            while True:
                next_value = self._round(current * f)
                if next_value <= self.MIN_THRESHOLD or next_value == current:
                    break

                self._clip_set(scene, prop, next_value)
                reset_to_frame(context, start_frame)
                length = self._detect_track_length(context, start_frame)

                if length >= target_length:
                    new_min = next_value
                    new_start = prev_value
                    self._clip_set(scene, prop, new_start)
                    self._log(f"[AutoCalib][{prop}] hit|min={new_min:.6f}|start={new_start:.6f}")
                    self._log(f"[AutoCalib][{prop}] gate→{new_start:.6f}")
                    return new_min, new_start, True, best_length

                prev_value = current
                current = next_value

            if current <= self.MIN_THRESHOLD:
                break

        self._log(f"[AutoCalib][{prop}] nohit")
        return self.MIN_THRESHOLD, start_value, False, best_length

    # ----------------------------------------------------
    # Haupttest (Paar) - mit Gate
    # ----------------------------------------------------
    def _downward_search_pair(self, context, start_frame: int, prop_a: str, prop_b: str, target_length: int,
                              start_a: float = 1.0, start_b: float = 1.0):
        scene = context.scene
        cur_a, cur_b = start_a, start_b
        prev_a, prev_b = cur_a, cur_b
        best_length = -1
        new_min_a = new_min_b = self.MIN_THRESHOLD
        new_start_a, new_start_b = start_a, start_b

        self._log(f"[AutoCalib][{prop_a},{prop_b}] start=({start_a:.6f},{start_b:.6f})")

        for f in self._down_steps:
            while True:
                next_a = self._round(cur_a * f)
                next_b = self._round(cur_b * f)
                if next_a <= self.MIN_THRESHOLD and next_b <= self.MIN_THRESHOLD:
                    break
                if next_a == cur_a and next_b == cur_b:
                    break

                self._clip_set(scene, prop_a, next_a)
                self._clip_set(scene, prop_b, next_b)
                reset_to_frame(context, start_frame)
                length = self._detect_track_length(context, start_frame)

                if length >= target_length:
                    new_min_a, new_min_b = next_a, next_b
                    new_start_a, new_start_b = prev_a, prev_b
                    self._clip_set(scene, prop_a, new_start_a)
                    self._clip_set(scene, prop_b, new_start_b)
                    self._log(f"[AutoCalib][{prop_a},{prop_b}] hit|min=({new_min_a:.6f},{new_min_b:.6f})|start=({new_start_a:.6f},{new_start_b:.6f})")
                    self._log(f"[AutoCalib][{prop_a},{prop_b}] gate→({new_start_a:.6f},{new_start_b:.6f})")
                    return (new_min_a, new_min_b), (new_start_a, new_start_b), True, best_length

                prev_a, prev_b = cur_a, cur_b
                cur_a, cur_b = next_a, next_b

            if cur_a <= self.MIN_THRESHOLD and cur_b <= self.MIN_THRESHOLD:
                break

        self._log(f"[AutoCalib][{prop_a},{prop_b}] nohit")
        return (self.MIN_THRESHOLD, self.MIN_THRESHOLD), (start_a, start_b), False, best_length

    # ----------------------------------------------------
    # rot_thresh_y automatisch ableiten
    # ----------------------------------------------------
    def _auto_set_rot_thresh_y(self, context):
        scene = context.scene
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if not clip or not hasattr(scene, "kaiserlich_rot_thresh_x"):
            return
        ha, va = clip.size
        if not va:
            return
        rx = float(getattr(scene, "kaiserlich_rot_thresh_x"))
        ry = min(1.0, self._round(rx * (ha / va)))
        setattr(scene, "kaiserlich_rot_thresh_y", ry)
        scene.update_tag()

    # ----------------------------------------------------
    # Ausführung
    # ----------------------------------------------------
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

        selected = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        for tr in tracking.tracks:
            tr.select = False

        def _restore():
            for tr in tracking.tracks:
                tr.select = (tr.name in selected)

        start_frame = get_start_frame(context)

        # Init: alle auf 1.0
        for p in self._single_props:
            if hasattr(scene, p):
                self._clip_set(scene, p, 1.0)
        for a, b in self._pair_props:
            if hasattr(scene, a) and hasattr(scene, b):
                self._clip_set(scene, a, 1.0)
                self._clip_set(scene, b, 1.0)

        reset_to_frame(context, start_frame)
        baseline_length = self._detect_track_length(context, start_frame)
        self._log(f"[AutoCalib] baseline={baseline_length}")

        # Einzel-Thresholds
        for prop in self._single_props:
            if not hasattr(scene, prop):
                continue
            improvement, target_length = self._short_test_single(context, start_frame, prop)
            if not improvement:
                continue

            start_val = self._next_start.get(prop, 1.0)
            new_min, new_start, hit, _ = self._downward_search_single(context, start_frame, prop, target_length, start_value=start_val)
            if hit:
                self._next_start[prop] = new_start
                self._log(f"[AutoCalib][{prop}] gate ✓")
            else:
                self._clip_set(scene, prop, 1.0)
                self._log(f"[AutoCalib][{prop}] no gate")

        # Doppel-Thresholds
        for prop_a, prop_b in self._pair_props:
            if not (hasattr(scene, prop_a) and hasattr(scene, prop_b)):
                continue
            improvement, target_length = self._short_test_pair(context, start_frame, prop_a, prop_b)
            if not improvement:
                continue

            start_a = self._next_start.get(prop_a, 1.0)
            start_b = self._next_start.get(prop_b, 1.0)
            (new_min_a, new_min_b), (new_start_a, new_start_b), hit, _ = self._downward_search_pair(
                context, start_frame, prop_a, prop_b, target_length, start_a=start_a, start_b=start_b
            )
            if hit:
                self._next_start[prop_a] = new_start_a
                self._next_start[prop_b] = new_start_b
                self._log(f"[AutoCalib][{prop_a},{prop_b}] gate ✓")
            else:
                self._clip_set(scene, prop_a, 1.0)
                self._clip_set(scene, prop_b, 1.0)
                self._log(f"[AutoCalib][{prop_a},{prop_b}] no gate")

        reset_to_frame(context, start_frame)
        _restore()
        self._auto_set_rot_thresh_y(context)
        self.report({'INFO'}, "Auto-Calibrate abgeschlossen.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)


if __name__ == "__main__":
    register()
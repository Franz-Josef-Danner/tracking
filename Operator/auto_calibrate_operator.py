import bpy
from typing import Tuple
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.playhead_helper import get_start_frame, reset_to_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Threshold-Kalibrierung mit deterministischer Stufenlogik und Gate-Steuerung"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Auto-Calibrate Thresholds"
    bl_description = "Mehrstufige Downward-Kalibrierung mit Gate-Steuerung für Einzel- und Doppel-Thresholds."
    bl_options = {"REGISTER", "UNDO"}

    verbose: bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Zeigt minimalistische Logs für Threshold-Test, Segmentlänge und aktive Stufe"
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
        len_neutral = self._detect_track_length(context, start_frame)
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop, self.MIN_THRESHOLD)
        len_min = self._detect_track_length(context, start_frame)
        return (len_min > len_neutral), max(len_neutral, len_min)

    # ----------------------------------------------------
    # Kurztest (Paar)
    # ----------------------------------------------------
    def _short_test_pair(self, context, start_frame: int, prop_a: str, prop_b: str) -> Tuple[bool, int]:
        scene = context.scene
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, 1.0)
        self._clip_set(scene, prop_b, 1.0)
        len_neutral = self._detect_track_length(context, start_frame)
        reset_to_frame(context, start_frame)
        self._clip_set(scene, prop_a, self.MIN_THRESHOLD)
        self._clip_set(scene, prop_b, self.MIN_THRESHOLD)
        len_min = self._detect_track_length(context, start_frame)
        return (len_min > len_neutral), max(len_neutral, len_min)

    # ----------------------------------------------------
    # Haupttest (Einzel)
    # ----------------------------------------------------
    def _main_test_single(self, context, start_frame: int, prop: str, target_length: int, start_value: float = 1.0):
        scene = context.scene
        current = start_value
        gate = None
        stage = 1
        self._next_start[prop] = start_value

        while True:
            next_value = self._round(current * 0.5)
            if next_value < self.MIN_THRESHOLD:
                next_value = self.MIN_THRESHOLD

            self._clip_set(scene, prop, next_value)
            reset_to_frame(context, start_frame)
            seg_len = self._detect_track_length(context, start_frame)

            if self.verbose:
                print(f"[{prop}] thr={next_value:.8f} len={seg_len} stage={stage}")

            # Neuer Zielwert
            if seg_len > target_length:
                target_length = seg_len
                gate = next_value
                self._next_start[prop] = current
                # nächste Stufe vorbereiten
                self._clip_set(scene, prop, current)
                stage += 1
                continue

            # Gate unterschritten
            if gate and next_value < gate:
                self._clip_set(scene, prop, self._next_start[prop])
                stage += 1
                continue

            # Ende
            if next_value <= self.MIN_THRESHOLD:
                break

            current = next_value

        return gate, target_length

    # ----------------------------------------------------
    # Haupttest (Paar)
    # ----------------------------------------------------
    def _main_test_pair(self, context, start_frame: int, prop_a: str, prop_b: str, target_length: int):
        scene = context.scene
        # Phase 1: A fix, B testet
        self._clip_set(scene, prop_a, self.MIN_THRESHOLD)
        self._main_test_single(context, start_frame, prop_b, target_length)
        # Phase 2: B fix, A testet
        self._clip_set(scene, prop_b, self.MIN_THRESHOLD)
        self._main_test_single(context, start_frame, prop_a, target_length)

    # ----------------------------------------------------
    # Ableitung rot_thresh_y
    # ----------------------------------------------------
    def _auto_set_rot_thresh_y(self, context):
        scene = context.scene
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
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
    # Execute
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

        # Init
        for p in self._single_props:
            if hasattr(scene, p):
                self._clip_set(scene, p, 1.0)
        for a, b in self._pair_props:
            if hasattr(scene, a) and hasattr(scene, b):
                self._clip_set(scene, a, 1.0)
                self._clip_set(scene, b, 1.0)

        reset_to_frame(context, start_frame)

        # Einzel-Thresholds
        for prop in self._single_props:
            if not hasattr(scene, prop):
                continue
            improvement, target_length = self._short_test_single(context, start_frame, prop)
            if not improvement:
                continue
            start_val = self._next_start.get(prop, 1.0)
            self._main_test_single(context, start_frame, prop, target_length, start_value=start_val)

        # Doppel-Thresholds
        for prop_a, prop_b in self._pair_props:
            if not (hasattr(scene, prop_a) and hasattr(scene, prop_b)):
                continue
            improvement, target_length = self._short_test_pair(context, start_frame, prop_a, prop_b)
            if not improvement:
                continue
            self._main_test_pair(context, start_frame, prop_a, prop_b, target_length)

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
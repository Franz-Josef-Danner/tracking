# Operator/Master/master_deep_test_operator.py
import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set

from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect_adapt_helper import run_detect_adapt
from ...Helper.util_clip import get_active_clip
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.delete import delete_tracks_by_names
from ...Helper.get_clip_context import get_clip_context


@dataclass
class DeepTestState:
    """Encapsulates all runtime data of the Deep Test process."""
    counter: int = 0
    stop_flag: bool = False
    
    base_value: float = 0.0
    reference_value: float = 0.0
    start: float = 0.0
    lower_limit: float = 0.0
    step: float = 0.0
    next_val: float = 0.0

    old_tracks: Set[str] = field(default_factory=set)
    new_tracks: Set[str] = field(default_factory=set)
    all_tracks: Set[str] = field(default_factory=set)


class KAISERLICHTRACKER_OT_master_deep_test_operator(Operator):
    bl_idname = "kaiserlichtracker.master_deep_test_operator"
    bl_label = "Kaiserlich Tracker: Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        self.state = DeepTestState()
        self.state.next_val = 0.0
        self.state.stop_flag = False

        print("\n[DeepTest][Init] 🔧 Starte Deep-Test-Sequenz ...")

        while True:
            self._set_threshold(context)
            print("[DeepTest][Init] Thresholds zurückgesetzt (alle = 1.0).")

            # Main loop through all threshold steps
            while not self.state.stop_flag:
                print(f"\n[DeepTest][Step {self.state.step}] --- Neue Threshold-Phase gestartet ---")
                self._set_step_threshold(context)

                if self.state.stop_flag:
                    print("[DeepTest] ✅ Alle Threshold-Phasen abgeschlossen.")
                    break

                print(f"[DeepTest][Step {self.state.step}] Aktueller Testwert: {self.state.next_val:.8f}")
                self.state.next_val = 1.0
                self._set_step_threshold(context)
                print(f"[DeepTest][Track] 🚀 Tracking mit Threshold={self.state.next_val:.8f}")
                self._track(context)
                print(f"[DeepTest][Result] Referenzwert: {self.state.reference_value:.3f}")

                self.state.base_value = self.state.reference_value
                self.state.start = self.state.next_val
                self.state.next_val = 0.00001
                self._set_step_threshold(context)
                self.state.lower_limit = self.state.next_val
                print(f"[DeepTest][Range] Start={self.state.start:.8f}, LowerLimit={self.state.lower_limit:.8f}")
                self._track(context)
                print(f"[DeepTest][Result] Referenzwert nach Low={self.state.reference_value:.3f}")

                if self.state.reference_value <= self.state.base_value:
                    print(f"[DeepTest][Adjust] Kein Anstieg – Schritt {self.state.step + 1}")
                    self.state.step = self.state.step + 1
                    continue

                self.state.step = abs(self.state.start - self.state.lower_limit) / 2.0
                self.state.next_val = self.state.next_val + self.state.step
                print(f"[DeepTest][Calc] Neuer Step-Wert: {self.state.step:.8f} → NextVal={self.state.next_val:.8f}")
                self._set_step_threshold(context)
                self._track(context)
                print(f"[DeepTest][Result] Nach Mid-Test: {self.state.reference_value:.3f}")

                if self.state.reference_value < self.state.base_value:
                    print("[DeepTest][Decision] ⬇️ Wert gefallen → Minus-Threshold-Richtung")
                    self._minus_thresh(context)
                else:
                    if self.state.reference_value > self.state.base_value:
                        print("[DeepTest][Decision] ⬆️ Wert gestiegen → Plus-Threshold-Richtung")
                        self.state.base_value = self.state.reference_value
                        self._plus_thresh(context)
                    else:
                        print("[DeepTest][Decision] ⏸ Keine Änderung → Bleibe bei Plus-Richtung")
                        self._plus_thresh(context)

        print("[DeepTest] ✅ Alle Threshold-Stufen abgeschlossen – Prozess beendet.")
        return {'FINISHED'}


    def _set_threshold(self, context: Context) -> None:
        scene = context.scene
        # Baseline reset: all threshold parameters set to 1.0
        scene.kaiserlich_rot_thresh_x = 1.0
        scene.kaiserlich_rot_thresh_y = 1.0
        scene.kaiserlich_scale_thresh_min = 1.0
        scene.kaiserlich_scale_thresh_max = 1.0
        scene.kaiserlich_rot_scale_thresh_rot = 1.0
        scene.kaiserlich_rot_scale_thresh_scale = 1.0
        scene.kaiserlich_perspective_thresh = 1.0


    def _set_step_threshold(self, context: Context) -> None:
        clip = get_active_clip(context)
        scene = context.scene
        step = self.state.step
        val = self.state.next_val

        if step == 0:
            if clip:
                width, height = clip.size
                y_val = min(1.0, val * (height / width if width else 1.0))
                scene.kaiserlich_rot_thresh_x = float(val)
                scene.kaiserlich_rot_thresh_y = float(y_val)
                print(f"[DeepTest][Set] 🔸 rot_xy → X={val:.8f}, Y={y_val:.8f}")
            return

        elif step == 1:
            scene.kaiserlich_scale_thresh_min = float(val)
            scene.kaiserlich_scale_thresh_max = float(min(1.0, val * 1.1))
            print(f"[DeepTest][Set] 🔸 scale_min/max → Min={scene.kaiserlich_scale_thresh_min:.8f}, Max={scene.kaiserlich_scale_thresh_max:.8f}")
            return

        elif step == 2:
            scene.kaiserlich_rot_scale_thresh_rot = float(val)
            scene.kaiserlich_rot_scale_thresh_scale = 0.0
            print(f"[DeepTest][Set] 🔸 rot_scale (Rotation) → Rot={val:.8f}")
            return

        elif step == 3:
            scene.kaiserlich_rot_scale_thresh_rot = 0.0
            scene.kaiserlich_rot_scale_thresh_scale = float(val)
            print(f"[DeepTest][Set] 🔸 rot_scale (Scale) → Scale={val:.8f}")
            return

        elif step == 4:
            scene.kaiserlich_perspective_thresh = float(val)
            print(f"[DeepTest][Set] 🔸 perspective → {val:.8f}")
            return

        elif step >= 5:
            print("[DeepTest][Stop] 🛑 Threshold-Test abgeschlossen.")
            self.state.stop_flag = True
            return


    def _track(self, context: Context):
        clip = get_active_clip(context)
        if not clip:
            print("[DeepTest][Track] ⚠️ Kein aktiver Clip gefunden.")
            return
    
        old_data = snapshot_active_markers(context)
        print(f"[DeepTest][Track] Snapshot vor Detect: {len(old_data)} Marker erfasst.")

        try:
            run_detect_adapt(context)
        except Exception:
            print("[DeepTest][Track] ⚠️ run_detect_adapt() fehlgeschlagen.")
            pass

        import time
        time.sleep(0.1)
        bpy.context.view_layer.update()

        all_data = snapshot_active_markers(context)
        print(f"[DeepTest][Track] Snapshot nach Detect: {len(all_data)} Marker erfasst.")

        old_names = {d["track"] for d in old_data if isinstance(d, dict) and "track" in d}
        all_names = {d["track"] for d in all_data if isinstance(d, dict) and "track" in d}
    
        self.state.old_tracks = old_names
        self.state.all_tracks = all_names
        self.state.new_tracks = all_names - old_names
        print(f"[DeepTest][Track] Neue Tracks erkannt: {len(self.state.new_tracks)}")

        self._track_forward_with_limits(context)

        scene = context.scene
        self.state.reference_value = get_total_track_length(
            context,
            start_frame=scene.frame_start,
            include_names=self.state.new_tracks
        )
        print(f"[DeepTest][Metric] 📏 Gesamtlänge neue Tracks: {self.state.reference_value:.3f}")

        if self.state.new_tracks:
            delete_tracks_by_names(context, track_names=self.state.new_tracks)
            print("[DeepTest][Cleanup] 🧹 Neue Tracks gelöscht.")


    def _plus_thresh(self, context: Context) -> None:
        print("[DeepTest][Adjust] ➕ Plus-Richtung gestartet.")
        while True:
            self.state.lower_limit = self.state.next_val
            step = abs(self.state.start - self.state.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][+] Step={step:.8f}, NextVal={self.state.next_val:.8f}")
            if step > 0.0001:
                self.state.next_val = self.state.next_val + step
                self._set_step_threshold(context)
                self._track(context)

                if self.state.reference_value >= self.state.base_value:
                    if self.state.reference_value > self.state.base_value:
                        print("[DeepTest][Adjust][+] Wert verbessert → weiter erhöhen.")
                        self.state.base_value = self.state.reference_value
                        continue
                    else:
                        continue
                else:
                    print("[DeepTest][Adjust][+] Wert verschlechtert → Minusrichtung.")
                    self._minus_thresh(context)
            else:
                print("[DeepTest][Adjust][+] Schrittgröße zu klein → Weiter zur nächsten Stufe.")
                self.state.step = self.state.step + 1
                return


    def _minus_thresh(self, context: Context) -> None:
        print("[DeepTest][Adjust] ➖ Minus-Richtung gestartet.")
        while True:
            self.state.start = self.state.next_val
            step = abs(self.state.start - self.state.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][-] Step={step:.8f}, NextVal={self.state.next_val:.8f}")
            if step > 0.0001:
                self.state.next_val = self.state.next_val - step
                self._set_step_threshold(context)
                self._track(context)

                if self.state.reference_value < self.state.base_value:
                    print("[DeepTest][Adjust][-] Kein Fortschritt → weiter reduzieren.")
                    continue
                else:
                    if self.state.reference_value > self.state.base_value:
                        print("[DeepTest][Adjust][-] Wert verbessert → Plusrichtung.")
                        self.state.base_value = self.state.reference_value
                        self._plus_thresh(context)
                    else:
                        print("[DeepTest][Adjust][-] Stabil → Plusrichtung.")
                        self._plus_thresh(context)
            else:
                print("[DeepTest][Adjust][-] Schrittgröße zu klein → Weiter zur nächsten Stufe.")
                self.state.step = self.state.step + 1
                return


    def _track_forward_with_limits(
        self,
        context: Context,
        *,
        max_frames: int = 50,
        min_distance_to_end: int = 50,
        log: bool = True
    ) -> int:
        scene = context.scene
        clip = get_active_clip(context)
        if not clip or not getattr(clip, "tracking", None):
            return 0

        end_frame = int(scene.frame_end)
        current_frame = int(scene.frame_current)
        original_frame = current_frame
        remaining = end_frame - current_frame

        if remaining < min_distance_to_end:
            new_start = max(scene.frame_start, end_frame - min_distance_to_end)
            reset_to_frame(context, new_start)
            scene.frame_current = new_start

        tracking = clip.tracking
        active_tracks = [t.name for t in tracking.tracks if getattr(t, "select", False)]
        if not active_tracks:
            print("[DeepTest][TrackFwd] ⚠️ Keine aktiven Tracks gefunden.")
            return 0

        ctx_override = get_clip_context()
        if not ctx_override:
            print("[DeepTest][TrackFwd] ⚠️ Kein gültiger Kontext.")
            return 0

        frames_tracked = 0
        for _ in range(max_frames):
            if current_frame >= end_frame:
                break

            active_tracks, dropped = filter_active_tracks_at_frame(context, active_tracks, current_frame)
            if not active_tracks:
                break

            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception:
                pass

            with bpy.context.temp_override(**ctx_override):
                result = bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False)
            if 'CANCELLED' in str(result):
                break

            frames_tracked += 1
            current_frame += 1
            scene.frame_current = current_frame

            try:
                context.space_data.clip_user.frame_current = current_frame
            except Exception:
                pass

        total_len = get_total_track_length(context, start_frame=scene.frame_start, include_names=active_tracks)
        print(f"[DeepTest][TrackFwd] 🧭 Vorwärts getrackt: {frames_tracked} Frames, Länge={total_len:.3f}")

        try:
            reset_to_frame(context, original_frame)
            scene.frame_current = original_frame
        except Exception:
            pass

        return frames_tracked

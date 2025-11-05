# Operator/Master/master_deep_test_operator.py
import bpy
from bpy.types import Operator, Context
from dataclasses import dataclass, field
from typing import Set
import time

from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect_adapt_helper import run_detect_adapt
from ...Helper.util_clip import get_active_clip
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.delete import delete_tracks_by_names
from ...Helper.get_clip_context import get_clip_context
# Fortschrittsanzeige
from ...Helper.ui_progress import set_progress

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
    converter: float = 0.0
    rot_thresh_x = 1.0
    rot_thresh_y = 1.0
    scale_thresh_min = 1.0
    scale_thresh_max = 1.0
    rot_scale_thresh_rot = 1.0
    rot_scale_thresh_scale = 1.0
    perspective_thresh = 1.0
    
    old_tracks: Set[str] = field(default_factory=set)
    new_tracks: Set[str] = field(default_factory=set)
    all_tracks: Set[str] = field(default_factory=set)
    # --- Modal Step Machine ---
    phase: str = "INIT"          # INIT -> STEP_START -> STEP_TEST_HIGH -> STEP_TEST_LOW -> STEP_MID -> DECIDE -> ADJUST_PLUS/MINUS -> NEXT_STEP -> DONE
    substep: int = 0             # feingranulare Schritte innerhalb einer Phase
    yield_flag: bool = False     # UI-Yield Steuerung

class KAISERLICHTRACKER_OT_master_deep_test_operator(Operator):
    bl_idname = "kaiserlichtracker.master_deep_test_operator"
    bl_label = "Kaiserlich Tracker: Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None

    # --- UI sichtbarer Converter-Wert ---
    converter: bpy.props.FloatProperty(
        name="Converter",
        description="Aktueller Zwischenwert zur Fortschrittsanzeige",
        default=0.0,
        min=0.0,
        max=1.0
    )

    def execute(self, context: Context):
        self.state = DeepTestState()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        print("[DeepTest][Modal] 🚀 Gestartet – UI bleibt aktiv.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            print("[DeepTest][Modal] ❌ Abgebrochen.")
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            # sichtbares Progress-Update pro Tick
            self._ui_progress(context)
            if self.state.stop_flag or self.state.phase == "DONE":
                print("[DeepTest][Modal] ✅ Alle Threshold-Stufen abgeschlossen – Prozess beendet.")
                self.cancel(context)
                return {'FINISHED'}

            try:
                self._process_step_incremental(context)
            except Exception as e:
                print(f"[DeepTest][Modal] ⚠️ Fehler: {e}")
                self.cancel(context)
                return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

    def _process_step_incremental(self, context: Context):
        """Atomare, tick-weise Ausführung – kein Blocking."""
        s = self.state
        if s.phase == "INIT":
            print(f"\n[DeepTest][Step {s.step}] --- Neue Threshold-Phase gestartet ---")
            s.phase = "STEP_START"
            return

        if s.phase == "STEP_START":
            self._set_step_threshold(context)     # val aktuell (0)
            if s.stop_flag: return
            s.next_val = 1.0
            self._set_step_threshold(context)     # High
            s.phase = "STEP_TEST_HIGH"
            return

        if s.phase == "STEP_TEST_HIGH":
            self._track(context)                  # Blocking Tracking → aber nur 1x pro Tick aufgerufen
            print(f"[DeepTest][Result] Referenzwert: {s.reference_value:.3f}")
            s.base_value = s.reference_value
            s.start = s.next_val
            s.next_val = 0.00001
            self._set_step_threshold(context)     # Low
            s.lower_limit = s.next_val
            print(f"[DeepTest][Range] Start={s.start:.8f}, LowerLimit={s.lower_limit:.8f}")
            s.phase = "STEP_TEST_LOW"
            return

        if s.phase == "STEP_TEST_LOW":
            self._track(context)
            print(f"[DeepTest][Result] Referenzwert nach Low={s.reference_value:.3f}")
            if s.reference_value <= s.base_value:
                print(f"[DeepTest][Adjust] Kein Anstieg – Schritt {s.step + 1}")
                s.step += 1
                if s.step >= 5:
                    print("[DeepTest][Finalize] → Letzter Threshold-Set-Aufruf für Step>=5")
                    # Finalen Threshold schreiben
                    self._set_step_threshold(context)
                    s.phase = "DONE"
                    s.stop_flag = True
                else:
                    s.phase = "INIT"
                return
            s.base_value = s.reference_value
            s.converter = abs(s.start - s.lower_limit) / 2.0
            self.converter = s.converter
            s.next_val = s.next_val + s.converter
            print(f"[DeepTest][Calc] Neuer Step-Wert: {s.step:.8f} → NextVal={s.next_val:.8f}")
            self._set_step_threshold(context)     # Mid
            s.phase = "STEP_MID"
            return

        if s.phase == "STEP_MID":
            self._track(context)
            print(f"[DeepTest][Result] Nach Mid-Test: {s.reference_value:.3f}")
            if s.reference_value < s.base_value:
                print("[DeepTest][Decision] ⬇️ Wert gefallen → Minus-Threshold-Richtung")
                s.phase = "ADJUST_MINUS"
            elif s.reference_value > s.base_value:
                print("[DeepTest][Decision] ⬆️ Wert gestiegen → Plus-Threshold-Richtung")
                s.base_value = s.reference_value
                s.phase = "ADJUST_PLUS"
            else:
                print("[DeepTest][Decision] ⏸ Keine Änderung → Bleibe bei Plus-Richtung")
                s.phase = "ADJUST_PLUS"
            return

        if s.phase == "ADJUST_PLUS":
            # ein Inkrement der Plus-Richtung
            s.lower_limit = s.next_val
            conv = abs(s.start - s.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][+] converter={conv:.8f}, NextVal={s.next_val:.8f}")
            if conv > 0.00001:
                s.next_val = s.next_val + conv
                s.converter = conv
                self.converter = conv
                self._set_step_threshold(context)
                s.phase = "ADJUST_PLUS_TRACK"
            else:
                print("[DeepTest][Adjust][+] Schrittgröße zu klein → Weiter zur nächsten Stufe.")
                s.step += 1
                s.phase = "INIT" if s.step < 5 else "DONE"
                s.stop_flag = (s.phase == "DONE")
            return

        if s.phase == "ADJUST_PLUS_TRACK":
            self._track(context)
            if s.reference_value >= s.base_value:
                if s.reference_value > s.base_value:
                    print("[DeepTest][Adjust][+] Wert verbessert → weiter erhöhen.")
                    s.base_value = s.reference_value
                    s.phase = "ADJUST_PLUS"
                else:
                    s.phase = "ADJUST_PLUS"
            else:
                print("[DeepTest][Adjust][+] Wert verschlechtert → Minusrichtung.")
                s.phase = "ADJUST_MINUS"
            return

        if s.phase == "ADJUST_MINUS":
            s.start = s.next_val
            conv = abs(s.start - s.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][-] converter={conv:.8f}, NextVal={s.next_val:.8f}")
            if conv > 0.00001:
                s.next_val = s.next_val - conv
                s.converter = conv
                self.converter = conv
                self._set_step_threshold(context)
                s.phase = "ADJUST_MINUS_TRACK"
            else:
                print("[DeepTest][Adjust][-] Schrittgröße zu klein → Weiter zur nächsten Stufe.")
                s.step += 1
                if s.step >= 5:
                   print("[DeepTest][Finalize] → Letzter Threshold-Set-Aufruf für Step>=5")
                   self._set_step_threshold(context)  # <-- führt deinen finalen Block aus
                   s.phase = "DONE"
                   s.stop_flag = True
                else:
                   s.phase = "INIT"
                return

        if s.phase == "ADJUST_MINUS_TRACK":
            self._track(context)
            if s.reference_value < s.base_value:
                print("[DeepTest][Adjust][-] Kein Fortschritt → weiter reduzieren.")
                s.phase = "ADJUST_MINUS"
            else:
                if s.reference_value > s.base_value:
                    print("[DeepTest][Adjust][-] Wert verbessert → Plusrichtung.")
                    s.base_value = s.reference_value
                    s.phase = "ADJUST_PLUS"
                else:
                    print("[DeepTest][Adjust][-] Stabil → Plusrichtung.")
                    s.phase = "ADJUST_PLUS"
            return

        if s.phase == "DONE":
            self._finalize(context)
            return

    
    def _set_step_threshold(self, context: Context) -> None:
        clip = get_active_clip(context)
        scene = context.scene
        step = self.state.step
        val = self.state.next_val
    
        # Synchronisierung mit UI-Property
        converter = self.converter
        pro = (1 - converter) * 100
    
        # Fortschrittsanzeige – basiert auf live aktualisiertem Converter
        vale = min(100.0, ((step - converter + 1) / 5.0) * 100.0)
    
        set_progress(
            title=f"DeepTest: Step {int(step)} (progress={vale:d}%)",
        )
    
        # Optional in Szene speichern, falls Panels darauf zugreifen:
        try:
            scene.kaiserlich_converter = converter
        except Exception:
            pass

                    
        if step == 0:
            if clip:
                width, height = clip.size
                y_val = min(1.0, val * (width / height if width else 1.0))
                scene.kaiserlich_rot_thresh_x = float(val)
                scene.kaiserlich_rot_thresh_y = float(y_val)
                self.state.rot_thresh_x = float(val)
                self.state.rot_thresh_y = float(y_val)
                scene.kaiserlich_scale_thresh_min = 1
                scene.kaiserlich_scale_thresh_max = 1
                scene.kaiserlich_rot_scale_thresh_rot = 1
                scene.kaiserlich_rot_scale_thresh_scale = 1
                scene.kaiserlich_perspective_thresh = 1
                print(f"[DeepTest][Set] 🔸 rot_xy → X={val:.8f}, Y={y_val:.8f}")
            return

        elif step == 1:
            scene.kaiserlich_rot_thresh_x = 1
            scene.kaiserlich_rot_thresh_y = 1
            scene.kaiserlich_scale_thresh_min = float(val)
            scene.kaiserlich_scale_thresh_max = float(min(1.0, val * 1.1))
            self.state.scale_thresh_min = float(val)
            self.state.scale_thresh_max = float(min(1.0, val * 1.1))
            scene.kaiserlich_rot_scale_thresh_rot = 1
            scene.kaiserlich_rot_scale_thresh_scale = 1
            scene.kaiserlich_perspective_thresh = 1
            print(f"[DeepTest][Set] 🔸 scale_min/max → Min={scene.kaiserlich_scale_thresh_min:.8f}, Max={scene.kaiserlich_scale_thresh_max:.8f}")
            return

        elif step == 2:
            scene.kaiserlich_rot_thresh_x = 1
            scene.kaiserlich_rot_thresh_y = 1
            scene.kaiserlich_scale_thresh_min = 1
            scene.kaiserlich_scale_thresh_max = 1
            scene.kaiserlich_rot_scale_thresh_rot = float(val)
            scene.kaiserlich_rot_scale_thresh_scale = 0.0
            self.state.rot_scale_thresh_rot = float(val)
            scene.kaiserlich_perspective_thresh = 1
            print(f"[DeepTest][Set] 🔸 rot_scale (Rotation) → Rot={val:.8f}")
            return

        elif step == 3:
            scene.kaiserlich_rot_thresh_x = 1
            scene.kaiserlich_rot_thresh_y = 1
            scene.kaiserlich_scale_thresh_min = 1
            scene.kaiserlich_scale_thresh_max = 1
            scene.kaiserlich_rot_scale_thresh_rot = 0.0
            scene.kaiserlich_rot_scale_thresh_scale = float(val)
            self.state.rot_scale_thresh_scale = float(val)
            scene.kaiserlich_perspective_thresh = 1
            print(f"[DeepTest][Set] 🔸 rot_scale (Scale) → Scale={val:.8f}")
            return

        elif step == 4:
            scene.kaiserlich_rot_thresh_x = 1
            scene.kaiserlich_rot_thresh_y = 1
            scene.kaiserlich_scale_thresh_min = 1
            scene.kaiserlich_scale_thresh_max = 1
            scene.kaiserlich_rot_scale_thresh_rot = 1
            scene.kaiserlich_rot_scale_thresh_scale = 1
            scene.kaiserlich_perspective_thresh = float(val)
            self.state.perspective_thresh = float(val)
            print(f"[DeepTest][Set] 🔸 perspective → {val:.8f}")
            return

        elif step >= 5:
            scene.kaiserlich_rot_thresh_x = self.state.rot_thresh_x
            scene.kaiserlich_rot_thresh_y = self.state.rot_thresh_y
            scene.kaiserlich_scale_thresh_min = self.state.scale_thresh_min
            scene.kaiserlich_scale_thresh_max = self.state.scale_thresh_max
            scene.kaiserlich_rot_scale_thresh_rot = self.state.rot_scale_thresh_rot
            scene.kaiserlich_rot_scale_thresh_scale = self.state.rot_scale_thresh_scale
            scene.kaiserlich_perspective_thresh = self.state.perspective_thresh
            print("[DeepTest][Stop] 🛑 Threshold-Test abgeschlossen.")
            self.state.stop_flag = True
            self.state.phase = "DONE"

            return

    
    def _track(self, context: Context):
        clip = get_active_clip(context)
        if not clip:
            print("[DeepTest][Track] ⚠️ Kein aktiver Clip gefunden.")
            return
    
        old_data = snapshot_active_markers(context)

        try:
            run_detect_adapt(context)
        except Exception:
            print("[DeepTest][Track] ⚠️ run_detect_adapt() fehlgeschlagen.")
            pass

        import time
        time.sleep(0.1)
        bpy.context.view_layer.update()

        all_data = snapshot_active_markers(context)

        old_names = {d["track"] for d in old_data if isinstance(d, dict) and "track" in d}
        all_names = {d["track"] for d in all_data if isinstance(d, dict) and "track" in d}
    
        self.state.old_tracks = old_names
        self.state.all_tracks = all_names
        self.state.new_tracks = all_names - old_names

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

    def _finalize(self, context: Context):
        # Fortschrittsanzeige abschließen + UI refresh
        set_progress(title="DeepTest: abgeschlossen ✅", value=1.0)
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
        self.state.stop_flag = True

    def _ui_progress(self, context: Context):
        # Zentrales, nicht-blockierendes Redraw je Timer-Tick
        try:
            for area in context.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    area.tag_redraw()
        except Exception:
            pass

    def _plus_thresh(self, context: Context) -> None:
        print("[DeepTest][Adjust] ➕ Plus-Richtung gestartet.")
        while True:
            self.state.lower_limit = self.state.next_val
            converter = abs(self.state.start - self.state.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][+] converter={converter:.8f}, NextVal={self.state.next_val:.8f}")
            if converter > 0.00001:
                self.state.next_val = self.state.next_val + converter
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
            converter = abs(self.state.start - self.state.lower_limit) / 2.0
            print(f"[DeepTest][Adjust][-] converter={converter:.8f}, NextVal={self.state.next_val:.8f}")
            if converter > 0.00001:
                self.state.next_val = self.state.next_val - converter
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

        try:
            reset_to_frame(context, original_frame)
            scene.frame_current = original_frame
        except Exception:
            pass

        return frames_tracked

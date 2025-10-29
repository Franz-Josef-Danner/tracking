# Operator/deep_test_operator.py
import bpy
import time
from typing import Any, Dict, Optional, Tuple, List, Set
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.util_scene import set_scene_props
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.newmarker import classify_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame

# ---- Szenen-Keys (Zielwerte pro Kategorie) ---------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- Reduktionsstufen: zuerst stark, dann fein ------------------------------
# Interpretation deiner Spezifikation:
#   Stufe1: -95%  → *0.05
#   Stufe2: -50%  → *0.5
#   Stufe3: -20%  → *0.8
#   Stufe4: -10%  → *0.9
#   Stufe5:  -5%  → *0.95
#   Stufe6:  -2%  → *0.98
#   Stufe7:  -1%  → *0.99
REDUCTION_STEPS = [0.05, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
MIN_THRESHOLD_VAL = 0.00001


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Deep Test: pro Kategorie Stufen *multiplikativ* absenken, bis Ziel erreicht/überboten.
       Erst dann zur nächsten Stufe wechseln. Detect-Logik wie DetectAdapt, Tracking modal sichtbar."""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------ Runtime State ------------------------
    _timer = None
    _scene: Optional[bpy.types.Scene] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _window = None
    _area = None
    _region = None
    _space = None

    _hz: int = 0
    _vc: int = 0
    _ratio_xy: float = 1.0  # hz/vc

    # DetectAdapt relevante Parameter
    _margin: int = 100
    _pattern_size: int = 50
    _search_size: int = 100
    _threshold_detect: float = 0.0001

    # Zielanzahl Marker (aus UI)
    _ef_target: int = 25
    _tolerance: float = 0.0

    # Frames
    _start_frame: int = 1
    _end_frame: int = 1
    _current_frame: int = 1

    # Modal-Phasensteuerung
    _phase: str = "init"
    _categories_queue: List[str] = []
    _current_category: Optional[str] = None  # "rot_xy" | "scale_min" | "scale_max" | "rot_scale_rot" | "rot_scale_scale" | "perspective"

    # Kategorie-Zielwerte
    _goal_step1: int = 0
    _goal_step2: int = 0
    _goal_step3: int = 0
    _goal_step4: int = 0

    # Stufen-/Cycle-Status
    _base_value: float = 1.0      # Anfangswert der aktuellen Stufe (wird bei Nicht-Erfolg auf current_value gesetzt)
    _current_step_index: int = 0  # Index in REDUCTION_STEPS
    _current_value: float = 1.0   # aktuell gesetzter Threshold
    _current_goal: int = 0        # bewegliches Ziel für die Kategorie

    # Bestwerte pro Kategorie
    _best_rot_x: float = 1.0
    _best_rot_y: float = 1.0
    _best_scale_min: float = 1.0
    _best_scale_max: float = 1.0
    _best_rot_scale_rot: float = 0.0
    _best_rot_scale_scale: float = 1.0
    _best_perspective: float = 1.0

    # DetectAdapt Loop-Variablen
    _detect_loop: int = 0
    _detect_loop_max: int = 8
    _pre_snapshot: List[Dict[str, Any]] = []
    _baseline_start_tracknames: Set[str] = set()
    _last_md: float = 100.0
    _last_new_names: List[str] = []
    _final_new_tracks: List[str] = []
    _deleted_old_total: int = 0

    # Tracking-Stop-Logik
    _processing_names: List[str] = []

    # ------------------------ Blender Operator ------------------------

    def execute(self, context: Context):
        self._scene = context.scene
        self._clip = get_active_clip(context)
        if self._clip is None:
            self.report({'ERROR'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        self._hz, self._vc = self._clip.size
        self._ratio_xy = (self._hz / self._vc) if self._vc else 1.0

        ts = getattr(self._clip, "tracking", None).settings if getattr(self._clip, "tracking", None) else None
        self._margin = getattr(ts, "margin", 100) if ts else 100
        self._pattern_size = getattr(ts, "pattern_size", 50) if ts else 50
        self._search_size = getattr(ts, "search_size", 100) if ts else 100
        self._threshold_detect = 0.0001

        self._ef_target = int(self._scene.kaiserlich_markers_per_frame)
        self._tolerance = max(1.0, self._ef_target * 0.10)

        self._start_frame = int(self._scene.frame_start)
        self._end_frame = int(self._scene.frame_end)
        self._current_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        self._scene.frame_current = self._current_frame

        self._pre_snapshot = snapshot_active_markers(context)
        self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}
        self._last_md = self._hz * 0.025

        self._goal_step1 = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0))
        self._goal_step2 = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0))
        self._goal_step3 = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0))
        self._goal_step4 = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0))

        self._categories_queue = []
        if self._goal_step1 > 0:
            self._categories_queue.append("rot_xy")
        if self._goal_step2 > 0:
            self._categories_queue.extend(["scale_min", "scale_max"])
        if self._goal_step3 > 0:
            self._categories_queue.extend(["rot_scale_rot", "rot_scale_scale"])
        if self._goal_step4 > 0:
            self._categories_queue.append("perspective")

        if not self._categories_queue:
            self.report({'INFO'}, "Deep Test: Keine Zielwerte gesetzt – nichts zu tun.")
            return {'CANCELLED'}

        print("\n[Kaiserlich Tracker][DeepTest] Starte modalen Deep-Threshold-Test …")
        print(f"[DeepTest][Init] targetMarkers={self._ef_target} (tol=±{self._tolerance:.1f}), "
              f"frames={self._start_frame}-{self._end_frame}, categories={self._categories_queue}")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        self._phase = "category_select"
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._cleanup_timer(context)
            print("[DeepTest][Modal] ❌ Abgebrochen.")
            self.report({'INFO'}, "Deep Test abgebrochen.")
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._phase == "category_select":
            if not self._categories_queue:
                return self._finish_success(context)
            self._current_category = self._categories_queue.pop(0)
            self._prepare_category(context)
            self._phase = "cycle_prepare"
            return {'RUNNING_MODAL'}

        if self._phase == "cycle_prepare":
            self._prepare_cycle_for_current_category(context)
            self._phase = "detect_loop"
            return {'RUNNING_MODAL'}

        if self._phase == "detect_loop":
            detect_done = self._detect_adapt_iteration(context)
            if detect_done:
                self._phase = "detect_finalize"
            return {'RUNNING_MODAL'}

        if self._phase == "detect_finalize":
            self._finalize_detection_select_new(context)
            self._phase = "track_step"
            return {'RUNNING_MODAL'}

        if self._phase == "track_step":
            tracking_done = self._track_step_modal(context)
            if tracking_done:
                self._phase = "cycle_finalize"
            return {'RUNNING_MODAL'}

        if self._phase == "cycle_finalize":
            decision = self._finalize_cycle_and_decide_next(context)
            if decision == "repeat_step":
                self._phase = "cycle_prepare"          # gleiche Stufe, neuer (niedrigerer) base_value
            elif decision == "next_step":
                self._phase = "cycle_prepare"          # nächste Stufe
            elif decision == "next_category":
                self._phase = "category_select"
            else:
                return self._finish_success(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ------------------------ Category/Cycle Control ------------------------

    def _prepare_category(self, context: Context):
        print(f"\n[DeepTest][Category] → {self._current_category}")

        # Reset Detect-State
        self._pre_snapshot = snapshot_active_markers(context)
        self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}
        self._last_md = self._load_or_interpolate_md_for_frame(self._scene, self._current_frame, self._hz * 0.025)
        self._detect_loop = 0
        self._deleted_old_total = 0
        self._final_new_tracks = []
        self._last_new_names = []
        self._processing_names = []

        # Ziel je Kategorie
        if self._current_category in ("rot_xy",):
            self._current_goal = self._goal_step1
        elif self._current_category in ("scale_min", "scale_max"):
            self._current_goal = self._goal_step2
        elif self._current_category in ("rot_scale_rot", "rot_scale_scale"):
            self._current_goal = self._goal_step3
        else:
            self._current_goal = self._goal_step4

        # Threshold-Startwerte je Kategorie (laut Spezifikation)
        if self._current_category == "rot_xy":
            set_scene_props(self._scene, kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0)
            self._base_value = 1.0  # X ist führend; Y folgt mit Ratio
        elif self._current_category == "scale_min":
            # scale_min wird getestet, scale_max bleibt deaktiviert (0.0)
            set_scene_props(self._scene,
                            kaiserlich_scale_thresh_min=1.0,
                            kaiserlich_scale_thresh_max=0.0)
            self._base_value = 1.0
        elif self._current_category == "scale_max":
            set_scene_props(self._scene, kaiserlich_scale_thresh_max=1.0)
            self._base_value = 1.0
        elif self._current_category == "rot_scale_rot":
            # Start: rot wird getestet (1.0), scale bleibt fix 0.0
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=1.0,
                            kaiserlich_rot_scale_thresh_scale=0.0)
            self._base_value = 1.0
        elif self._current_category == "rot_scale_rot":
            # Reset auf Anfangszustand der Kategorie:
            # rot = 1.0 (wird getestet), scale = 0.0 (fix)
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=1.0,
                            kaiserlich_rot_scale_thresh_scale=0.0)
            self._base_value = 1.0
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=1.0)
            self._base_value = 1.0

        self._current_step_index = 0  # beginne mit der ersten (stärksten) Stufe

    def _prepare_cycle_for_current_category(self, context: Context):
        """Setzt current_value = base_value * step_factor, capped by MIN."""
        step_factor = REDUCTION_STEPS[self._current_step_index]

        if self._current_category == "rot_xy":
            import math
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)

            hz = float(self._hz)
            vc = float(self._vc)
            ratio_vh = (vc / hz) if hz else 1.0

            # Neue Formel für rot_thresh_y
            try:
                delta = (math.log10(1 * 1_000_000) - math.log10(next_val * 1_000_000))
                adj = pow((delta * ratio_vh), 10) / 1_000_000
            except ValueError:
                adj = 0.0

            rot_x = next_val
            rot_y = rot_x + adj

            set_scene_props(self._scene,
                            kaiserlich_rot_thresh_x=rot_x,
                            kaiserlich_rot_thresh_y=rot_y)
            self._current_value = rot_x

        elif self._current_category == "scale_min":
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
            set_scene_props(self._scene, kaiserlich_scale_thresh_min=next_val)
            self._current_value = next_val

        elif self._current_category == "scale_max":
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
            set_scene_props(self._scene, kaiserlich_scale_thresh_max=next_val)
            self._current_value = next_val

        elif self._current_category == "rot_scale_rot":
            # base_value kann 0.0 starten; dennoch * step_factor → bleibt 0.0.
            # Damit tatsächliche Absenkung möglich ist, nehmen wir max(MIN, base*factor)
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=next_val,
                            kaiserlich_rot_scale_thresh_scale=0.0)
            self._current_value = next_val

        elif self._current_category == "rot_scale_scale":
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=0.0,
                            kaiserlich_rot_scale_thresh_scale=next_val)
            self._current_value = next_val

        elif self._current_category == "perspective":
            next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
            set_scene_props(self._scene, kaiserlich_perspective_thresh=next_val)
            self._current_value = next_val

        # Detect-Loop zurücksetzen
        self._pre_snapshot = snapshot_active_markers(context)
        self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}
        self._detect_loop = 0
        self._final_new_tracks = []
        self._last_new_names = []
        self._deleted_old_total = 0
        self._last_md = self._load_or_interpolate_md_for_frame(self._scene, self._current_frame, self._hz * 0.025)

        print(f"[DeepTest][Cycle] {self._current_category} | step={self._current_step_index+1}/{len(REDUCTION_STEPS)} "
              f"| base={self._base_value:.6f} → curr={self._current_value:.6f} (×{step_factor}) | goal={self._current_goal}")

    # ------------------------ DetectAdapt (1 Iteration pro TIMER) ------------------------

    def _detect_adapt_iteration(self, context: Context) -> bool:
        self._detect_loop += 1
        loop = self._detect_loop
        print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop} ---")
        print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {self._last_md:.2f}")

        detect_features(
            context,
            placement='FRAME',
            margin=self._margin,
            threshold=self._threshold_detect,
            min_distance=int(max(1, round(self._last_md)))
        )

        clip = getattr(context.space_data, 'clip', None)
        if clip and getattr(clip, 'tracking', None):
            for trk in clip.tracking.tracks:
                try:
                    trk.select = False
                except Exception:
                    pass

        post_snapshot = snapshot_active_markers(context)
        alte_marker, neue_marker = classify_markers(self._pre_snapshot, post_snapshot)

        print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker erkannt: {len(alte_marker)}")
        print(f"[Kaiserlich Tracker][DetectAdapt] Neue Marker erkannt: {len(neue_marker)}")
        if len(neue_marker) > 0:
            print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
        if len(alte_marker) > 0:
            print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])

        am = len(neue_marker)

        cleaned_new, deleted_old = cleanup_new_markers(
            context,
            alte_marker,
            neue_marker,
            pz=self._pattern_size,
            hz=self._hz,
            vc=self._vc
        )
        self._deleted_old_total += int(deleted_old)

        deleted_old_names = [m['track'] for m in alte_marker
                             if m['track'] not in [n['track'] for n in post_snapshot]]
        if deleted_old_names:
            print(f"[⚠️ Kaiserlich Tracker][DetectAdapt] WARNUNG: Alte Marker gelöscht: {deleted_old_names}")

        remaining = len(cleaned_new)
        print(f"[Kaiserlich Tracker][DetectAdapt] Nach Cleanup: {remaining} neue Marker übrig, {deleted_old} alte gelöscht")

        if abs(remaining - self._ef_target) <= self._tolerance:
            self._last_new_names = [m['track'] for m in cleaned_new]
            self._store_md_with_interpolation(self._scene, self._current_frame, self._last_md)
            return True

        if am > 0:
            ratio = self._ef_target / am
            factor = max(0.5, min(2.0, ratio))
            new_md = self._last_md / factor
            self._last_md = max(1.0, new_md)
        else:
            self._last_md = self._last_md * 1.5
            print("[Kaiserlich Tracker][DetectAdapt] Keine neuen Marker, erhöhe min_distance stark")

        if loop < self._detect_loop_max:
            self._last_new_names = [m['track'] for m in neue_marker]
            delete_tracks_by_names(context, self._last_new_names)
            print(f"[Kaiserlich Tracker][DetectAdapt] {len(self._last_new_names)} neue Marker gelöscht für nächsten Zyklus")
            time.sleep(0.05)
            return False

        self._last_new_names = [m['track'] for m in cleaned_new]
        self._store_md_with_interpolation(self._scene, self._current_frame, self._last_md)
        print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Max. Loops erreicht – übernehme aktuellen Zustand.")
        return True

    def _finalize_detection_select_new(self, context: Context):
        clip = getattr(context.space_data, 'clip', None)
        if not (clip and getattr(clip, 'tracking', None)):
            self._final_new_tracks = []
            self._processing_names = []
            return
        tracking = clip.tracking
        new_tracks = [trk for trk in tracking.tracks if trk.name not in self._baseline_start_tracknames]
        try:
            for trk in tracking.tracks: trk.select = False
            for new_trk in new_tracks: new_trk.select = True
        except Exception:
            pass
        self._final_new_tracks = [t.name for t in new_tracks]
        self._processing_names = list(self._final_new_tracks)
        print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")

    # ------------------------ Modal Tracking pro Cycle ------------------------

    def _track_step_modal(self, context: Context) -> bool:
        if not self._processing_names:
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            print("[DeepTest][Track] ✅ Keine aktiven Tracks – Cycle beendet.")
            return True

        self._scene.frame_current = self._current_frame
        self._space.clip_user.frame_current = self._current_frame

        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )
        if not success:
            print("[DeepTest][Track] ⚠️ Tracking-Fehler, Cycle wird beendet.")
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            return True

        if self._space.clip_user.frame_current == self._current_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame

        self._scene.frame_current = self._space.clip_user.frame_current
        self._current_frame = self._space.clip_user.frame_current

        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )

        if self._current_frame >= self._end_frame or not self._processing_names:
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            print(f"[DeepTest][Track] ✅ Cycle beendet. Total Track Length = {total_len}")
            return True

        return False

    # ------------------------ Cycle Finalisierung & Stufen-/Kategorie-Steuerung ------------------------

    def _finalize_cycle_and_decide_next(self, context: Context) -> str:
        measured = int(self._scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
        goal_before = self._current_goal

        # Cleanup: neue Tracks löschen & Playhead reset
        delete_tracks_by_names(context, self._final_new_tracks)
        self._final_new_tracks = []
        self._processing_names = []
        self._scene.frame_current = self._start_frame
        self._space.clip_user.frame_current = self._start_frame
        self._current_frame = self._start_frame

        # 1) Ziel erreicht/überboten → Bestwert setzen, SCENE-Thresholds schreiben, nächste Stufe
        if measured >= self._current_goal:
            self._current_goal = measured
            self._apply_best_value_for_category(current_val=self._current_value)
            self._reset_thresholds_after_cycle()               # „auf Anfangswert setzen“
            self._current_step_index += 1                      # nächste Stufe
            if self._current_step_index < len(REDUCTION_STEPS):
                print(f"[DeepTest][Eval] ✓ Ziel erreicht | measured={measured} >= goal={goal_before} | next step")
                return "next_step"
            else:
                print(f"[DeepTest][Eval] ✓ Ziel erreicht | Kategorie abgeschlossen")
                return "next_category"

        # 2) Ziel NICHT erreicht:
        #    2a) Unterschreitung Mindestwert → nächste Stufe
        if self._current_value <= MIN_THRESHOLD_VAL + 1e-12:
            self._reset_thresholds_after_cycle()
            self._current_step_index += 1
            if self._current_step_index < len(REDUCTION_STEPS):
                print(f"[DeepTest][Eval] ✗ Ziel verfehlt, MIN erreicht → next step")
                return "next_step"
            else:
                print(f"[DeepTest][Eval] ✗ Ziel verfehlt, MIN erreicht → Kategorie abgeschlossen")
                return "next_category"

        #    2b) Noch oberhalb MIN → gleiche Stufe wiederholen,
        #        dabei gilt: aktueller Wert wird neuer Anfangswert; in _prepare_cycle wird erneut * step_factor abgesenkt
        self._base_value = self._current_value
        self._reset_thresholds_after_cycle()  # vor neuem Detect sauber resetten
        print(f"[DeepTest][Eval] ↻ Ziel verfehlt | measured={measured} < goal={goal_before} | repeat same step with lower value")
        return "repeat_step"

    def _apply_best_value_for_category(self, current_val: float):
        if self._current_category == "rot_xy":
            import math
            self._best_rot_x = current_val

            hz = float(self._hz)
            vc = float(self._vc)
            ratio_vh = (vc / hz) if hz else 1.0

            try:
                delta = (math.log10(1 * 1_000_000) - math.log10(self._best_rot_x * 1_000_000))
                adj = pow((delta * ratio_vh), 10) / 1_000_000
            except ValueError:
                adj = 0.0

            self._best_rot_y = self._best_rot_x + adj

            set_scene_props(self._scene,
                            kaiserlich_rot_thresh_x=self._best_rot_x,
                            kaiserlich_rot_thresh_y=self._best_rot_y)

            print(f"[DeepTest][Write] rot_xy → x={self._best_rot_x:.6f}, "
                  f"y={self._best_rot_y:.6f} (Formel mit Log/Pow basierend auf Auflösung)")

        elif self._current_category == "scale_min":
            self._best_scale_min = current_val
            set_scene_props(self._scene, kaiserlich_scale_thresh_min=self._best_scale_min)
            print(f"[DeepTest][Write] scale_min → {self._best_scale_min:.6f}")

        elif self._current_category == "scale_max":
            self._best_scale_max = current_val
            set_scene_props(self._scene, kaiserlich_scale_thresh_max=self._best_scale_max)
            print(f"[DeepTest][Write] scale_max → {self._best_scale_max:.6f}")

        elif self._current_category == "rot_scale_rot":
            self._best_rot_scale_rot = current_val
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=self._best_rot_scale_rot,
                            kaiserlich_rot_scale_thresh_scale=0.0)
            print(f"[DeepTest][Write] rot_scale_rot → {self._best_rot_scale_rot:.6f} (scale fix 0)")

        elif self._current_category == "rot_scale_scale":
            self._best_rot_scale_scale = current_val
            set_scene_props(self._scene,
                            kaiserlich_rot_scale_thresh_rot=0.0,
                            kaiserlich_rot_scale_thresh_scale=self._best_rot_scale_scale)
            print(f"[DeepTest][Write] rot_scale_scale → {self._best_rot_scale_scale:.6f} (rot fix 0)")

        elif self._current_category == "perspective":
            self._best_perspective = current_val
            set_scene_props(self._scene, kaiserlich_perspective_thresh=self._best_perspective)
            print(f"[DeepTest][Write] perspective → {self._best_perspective:.6f}")

    def _reset_thresholds_after_cycle(self):
        if self._current_category == "rot_xy":
            set_scene_props(self._scene, kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0)
        elif self._current_category == "scale_min":
            set_scene_props(self._scene, kaiserlich_scale_thresh_min=1.0)
        elif self._current_category == "scale_max":
            set_scene_props(self._scene, kaiserlich_scale_thresh_max=1.0)
        elif self._current_category == "rot_scale_rot":
            set_scene_props(self._scene, kaiserlich_rot_scale_thresh_rot=0.0,
                            kaiserlich_rot_scale_thresh_scale=0.0)
        elif self._current_category == "rot_scale_scale":
            set_scene_props(self._scene, kaiserlich_rot_scale_thresh_rot=0.0,
                            kaiserlich_rot_scale_thresh_scale=1.0)
        elif self._current_category == "perspective":
            # bleibt nach erfolgreichem Test gesetzt; hier kein Reset nötig
            pass

    # ------------------------ min_distance Speicher/Interpolation ------------------------

    def _load_or_interpolate_md_for_frame(self, scene: bpy.types.Scene, frame_num: int, fallback_md: float) -> float:
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                return float(md_dict[str(frame_num)])
            if "known_frames" in md_dict and len(md_dict["known_frames"]) >= 2:
                known = sorted(md_dict["known_frames"])
                prev_frames = [f for f in known if f < frame_num]
                next_frames = [f for f in known if f > frame_num]
                if prev_frames and next_frames:
                    f1 = max(prev_frames)
                    f2 = min(next_frames)
                    v1 = float(md_dict[str(f1)])
                    v2 = float(md_dict[str(f2)])
                    t = (frame_num - f1) / (f2 - f1)
                    return v1 + (v2 - v1) * t
        return float(fallback_md)

    def _store_md_with_interpolation(self, scene: bpy.types.Scene, frame_num: int, md_value: float) -> None:
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        known_list = list(md_dict.get("known_frames", []))
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = float(md_value)

        if len(known_list) > 1:
            for i in range(len(known_list) - 1):
                f_start = known_list[i]
                f_end = known_list[i + 1]
                if f_end - f_start < 2:
                    continue
                v_start = float(md_dict[str(f_start)])
                v_end = float(md_dict[str(f_end)])
                for f in range(f_start + 1, f_end):
                    t = (f - f_start) / float(f_end - f_start)
                    md_dict[str(f)] = float(v_start + (v_end - v_start) * t)

    # ------------------------ Abschluss ------------------------

    def _finish_success(self, context: Context):
        self._cleanup_timer(context)
        print("[DeepTest][Modal] ✅ Deep Test abgeschlossen.")
        self.report({'INFO'}, "Deep Test abgeschlossen.")
        return {'FINISHED'}

    def _cleanup_timer(self, context: Context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)

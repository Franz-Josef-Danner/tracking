# Operator/deep_test_operator.py
import bpy
import time
import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple, Set
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.scene import get_end_frame
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.newmarker import classify_markers
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.track_length_helper import get_total_track_length
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.util_scene import set_scene_props
from ..Helper.init_detect_state import init_detect_state
from ..Helper.reset_helper import reset_all_thresholds
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.filter_and_delete_tracks import filter_and_delete_tracks

# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"

# ---- Reduktions-Stufen ------------------------------------------------------
REDUCTION_STEPS = [0.05, 0.5, 0.8, 0.9, 0.95, 0.98, 0.99]
MIN_THRESHOLD_VAL = 0.00001

# ---- Interner Tracking-State (nicht-blockierend) ---------------------------
@dataclass
class _TrackState:
    active: bool = False
    current: int = 0
    end: int = 0
    active_names: List[str] = None
    total_len: int = -1  # -1 = noch nicht gemessen


class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Deep Threshold Test (Modal): führt pro Kategorie stufenweise Reduktion der Thresholds durch und testet jeweils."""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test"
    bl_options = {'REGISTER', 'UNDO'}

    # Laufzeitvariablen -------------------------------------------------------
    _timer = None
    _scene: Optional[bpy.types.Scene] = None
    _clip: Optional[bpy.types.MovieClip] = None
    _window = None
    _area = None
    _region = None
    _space = None

    _hz: int = 0
    _vc: int = 0
    _ratio_xy: float = 1.0

    _ef_target: int = 25
    _tolerance: float = 0.0

    _start_frame: int = 1
    _end_frame: int = 1
    _current_frame: int = 1

    _phase: str = "init"
    _categories_queue: List[str] = []
    _current_category: Optional[str] = None

    _current_step_index: int = 0
    _base_value: float = 1.0
    _current_value: float = 1.0
    _current_goal: int = 0

    _detect_loop: int = 0
    _detect_loop_max: int = 8
    _pre_snapshot: List[Dict[str, Any]] = []
    _baseline_start_tracknames: Set[str] = set()
    _last_md: float = 100.0
    _processing_names: List[str] = []
    _final_new_tracks: List[str] = []

    _goal_map: Dict[str, int] = {}
    _best_thresholds: Dict[str, float] = {}
    _track_state: _TrackState = _TrackState()

    # Detect-Parameter (paritätisch zum Shorttest)
    _margin: int = 100
    _threshold: float = 0.0001
    _pattern_size: int = 50
    _search_size: int = 0
    # ------------------------------------------------------------------------
    def execute(self, context: Context):
        self._scene = context.scene
        self._clip = get_active_clip(context)
        if not self._clip:
            self.report({'ERROR'}, "Kein aktiver Clip gefunden.")
            return {'CANCELLED'}

        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Keine CLIP_EDITOR Area gefunden.")
            return {'CANCELLED'}

        self._hz, self._vc = self._clip.size
        self._ratio_xy = (self._hz / self._vc) if self._vc else 1.0
        self._ef_target = int(self._scene.kaiserlich_markers_per_frame)
        self._tolerance = max(1.0, self._ef_target * 0.10)
        self._start_frame = int(self._scene.frame_start)
        self._end_frame = int(get_end_frame(context))
        self._current_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        self._scene.frame_current = self._current_frame

        # Thresholds global auf 1.0 zurücksetzen (ShortTest-Parität)
        try:
            reset_all_thresholds(context, active_props=[])
            print("[DeepTest][Init] Alle Thresholds auf 1.0 zurückgesetzt.")
        except Exception as e:
            print(f"[DeepTest][Init] ⚠️ Threshold-Reset fehlgeschlagen: {e!r}")
        # Detect-Parameter initialisieren (wie im Shorttest)
        try:
            _state = init_detect_state(context)
            self._hz = _state.get("hz", self._hz)
            self._vc = _state.get("vc", self._vc)
            self._margin = _state.get("margin", 100)
            self._pattern_size = _state.get("pattern_size", 50)
            self._search_size = _state.get("search_size", 0)
            self._threshold = _state.get("threshold", 0.0001)
            self._last_md = float(_state.get("min_distance", 100.0))
            # Frame-spezifisches md ggf. überschreiben
            _md_cache = self._scene.get("min_distance_values", {})
            if _md_cache:
                fn = str(self._scene.frame_current)
                if fn in _md_cache:
                    self._last_md = float(_md_cache[fn])
        except Exception as _e:
            print(f"[DeepTest][InitDetect] ⚠️ Fallback – init_detect_state fehlgeschlagen: {_e!r}")

        # Zielwerte laden
        # Zielwerte aus den Szenenvariablen ermitteln
        self._goal_map = {
            "rot_xy": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP1, 0)),
            "scale": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP2, 0)),
            "rot_scale_rot": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0)),
            "rot_scale_scale": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP3, 0)),
            "perspective": int(self._scene.get(SCENE_TOTAL_TRACK_LEN_STEP4, 0)),
        }

        # Nur Kategorien mit gesetztem Wert in die Queue aufnehmen
        self._categories_queue = [cat for cat, val in self._goal_map.items() if val > 0]

        if not self._categories_queue:
            print("[DeepTest] ❌ Keine Zielwerte gefunden – Abbruch.")
            self.report({'INFO'}, "Keine aktiven Szenenwerte – DeepTest übersprungen.")
            return {'CANCELLED'}

        print(f"[Kaiserlich Tracker][DeepTest] Starte Test für Kategorien mit gesetzten Szenenwerten: {self._categories_queue}")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._track_state = _TrackState(active=False, current=0, end=0, active_names=[], total_len=-1)
        self._phase = "category_select"
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._phase == "category_select":
            if not self._categories_queue:
                return self._finish(context)
            self._current_category = self._categories_queue.pop(0)
            self._prepare_category(context)
            self._phase = "threshold_cycle"
            return {'RUNNING_MODAL'}
        # Nicht-blockierendes Tracking: wenn Tracking aktiv, pro TIMER-Tick genau einen Schritt
        if self._phase == "tracking_tick":
            running = self._track_tick(context)
            if running:
                return {'RUNNING_MODAL'}
            # Tracking fertig → Ergebnis liegt in self._track_state.total_len
            self._phase = "threshold_cycle_evaluate"
            return {'RUNNING_MODAL'}

        # Auswertung nach beendetem Tracking innerhalb derselben Threshold-Stufe
        if self._phase == "threshold_cycle_evaluate":
            finished = self._evaluate_after_tracking(context)
            if finished:
                if self._categories_queue:
                    self._phase = "category_select"
                    return {'RUNNING_MODAL'}
                return self._finish(context)
            # sonst nächste Stufe derselben Kategorie
            self._phase = "threshold_cycle"
            return {'RUNNING_MODAL'}

        if self._phase == "threshold_cycle":
            finished = self._process_threshold_cycle(context)
            if finished:
                if self._categories_queue:
                    self._phase = "category_select"
                    return {'RUNNING_MODAL'}
                else:
                    return self._finish(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    def _prepare_category(self, context):
        print(f"\n[DeepTest][Category] → {self._current_category}")
        self._base_value = 1.0
        self._current_step_index = 0
        # Vergleichslänge direkt aus Szenenwert der Kategorie
        self._current_goal = int(self._goal_map.get(self._current_category, 0))
        self._best_thresholds[self._current_category] = 1.0
        self._pre_snapshot = snapshot_active_markers(context)
        self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}
        # Für jede Kategorie den frame-spezifischen md-Wert prüfen (wie Shorttest)
        try:
            _md_cache = self._scene.get("min_distance_values", {})
            if _md_cache:
                fn = str(self._scene.frame_current)
                if fn in _md_cache:
                    self._last_md = float(_md_cache[fn])
        except Exception:
            pass

        # Reset Thresholds auf 1.0 für die Kategorie
        if self._current_category == "rot_xy":
            set_scene_props(self._scene, kaiserlich_rot_thresh_x=1.0, kaiserlich_rot_thresh_y=1.0)
        elif self._current_category == "scale":
            set_scene_props(self._scene,
                kaiserlich_scale_thresh_min=1.0, kaiserlich_scale_thresh_max=1.0)
        elif self._current_category == "rot_scale_rot":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=1.0,
                kaiserlich_rot_scale_thresh_scale=0.0
            )
            print("[DeepTest][rot_scale_rot] Init ROT-Threshold-Test")

        elif self._current_category == "rot_scale_scale":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=0.0,
                kaiserlich_rot_scale_thresh_scale=1.0
            )
            print("[DeepTest][rot_scale_scale] Init SCALE-Threshold-Test")
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=1.0)

    # ------------------------------------------------------------------------
    def _process_threshold_cycle(self, context) -> bool:
        """Durchläuft die Threshold-Stufen sequentiell und prüft je Durchgang."""
        if self._current_step_index >= len(REDUCTION_STEPS):
            print(f"[DeepTest][{self._current_category}] Alle Reduktionsstufen abgeschlossen.")
            return True
    
        step_factor = REDUCTION_STEPS[self._current_step_index]
        next_val = max(MIN_THRESHOLD_VAL, self._base_value * step_factor)
        self._current_value = next_val
    
        # ---- Threshold setzen (Szene aktualisieren) ----------------------------
        if self._current_category == "rot_xy":
            # Neue Formel: kaiserlich_rot_thresh_y = min(1, kaiserlich_rot_thresh_x * (Vertikale / Horizontale Auflösung))
            y_val = min(1.0, next_val * (self._hz / self._vc))
            set_scene_props(
                self._scene,
                kaiserlich_rot_thresh_x=next_val,
                kaiserlich_rot_thresh_y=y_val
            )
    
        elif self._current_category == "scale":
            set_scene_props(self._scene,
                            kaiserlich_scale_thresh_min=next_val,
                            kaiserlich_scale_thresh_max=min(1,next_val * 1.1))
        elif self._current_category == "rot_scale_rot":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=next_val,
                kaiserlich_rot_scale_thresh_scale=0.0
            )
            print(f"[DeepTest][rot_scale_rot] ▶ Step {self._current_step_index+1}/{len(REDUCTION_STEPS)} | val={next_val:.6f}")

        elif self._current_category == "rot_scale_scale":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=0.0,
                kaiserlich_rot_scale_thresh_scale=next_val
            )
            print(f"[DeepTest][rot_scale_scale] ▶ Step {self._current_step_index+1}/{len(REDUCTION_STEPS)} | val={next_val:.6f}")
    
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=next_val)
    
        print(f"[DeepTest][{self._current_category}] Test Step {self._current_step_index + 1}/{len(REDUCTION_STEPS)}: "
              f"{next_val:.6f} (×{step_factor})")
    
        # ---- Detect (UI-non-blocking bleibt gewahrt) ---------------------------
        # ---- DetectAdapt-Parität (komplette Schleife aus ShortTest) ----------
        ef_target = int(self._scene.kaiserlich_markers_per_frame)
        tolerance = ef_target * 0.10
        last_md = float(self._last_md)

        pre_snapshot = snapshot_active_markers(context)
        baseline_names = {t.name for t in self._clip.tracking.tracks}

        reached = False
        for loop in range(self._detect_loop_max):
            print(f"\n[DeepTest][DetectAdapt] --- LOOP {loop+1} ---")
            print(f"[DeepTest][DetectAdapt] Aktuelles min_distance = {last_md:.2f}")
            detect_features(
                context,
                placement='FRAME',
                margin=self._margin,
                threshold=self._threshold,
                min_distance=int(max(1, round(last_md)))
            )
            post_snapshot = snapshot_active_markers(context)
            alte, neue = classify_markers(pre_snapshot, post_snapshot)
            cleaned_new, _ = cleanup_new_markers(context, alte, neue, pz=self._pattern_size, hz=self._hz, vc=self._vc)
            remaining = len(cleaned_new)
            diff = remaining - ef_target

            print(f"[DeepTest][DetectAdapt] {remaining} Marker → Ziel {ef_target} (±{tolerance:.0f})")
            if abs(diff) <= tolerance:
                print("[DeepTest][DetectAdapt] ✅ Ziel erreicht")
                reached = True
                break

            # Adaptive Anpassung min_distance (wie ShortTest)
            am = len(cleaned_new)
            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                last_md = max(1.0, last_md / factor)
            else:
                last_md *= 1.5

            if loop < self._detect_loop_max - 1:
                delete_tracks_by_names(context, [m['track'] for m in neue])
                time.sleep(0.05)

        self._last_md = last_md
        print(f"[DeepTest][DetectAdapt] Final min_distance = {self._last_md:.2f}")

        # Finale Marker selektieren
        self._final_new_tracks = [m['track'] for m in cleaned_new]
        for trk in getattr(self._clip.tracking, "tracks", []):
            trk.select = (trk.name in self._final_new_tracks)

        # View-Layer synchronisieren (ShortTest-Parität)
        try:
            bpy.context.view_layer.update()
        except:
            pass
    
        # ---- Tracking (nicht-blockierend) -------------------------------------
        self._track_start(context)          # Initialisierung des tick-basierten Trackings
        self._phase = "tracking_tick"       # Modal-Loop übernimmt jetzt per TIMER jeweils 1 Frame
        return False


    # ------------------------------------------------------------------------
    def _detect_adapt_cycle(self, context):
        """Führt einen kurzen Detect/Cleanup-Zyklus aus."""
        detect_features(context, placement='FRAME', margin=100, threshold=0.0001, min_distance=50)
        post_snapshot = snapshot_active_markers(context)
        alte, neue = classify_markers(self._pre_snapshot, post_snapshot)
        cleanup_new_markers(context, alte, neue, pz=50, hz=self._hz, vc=self._vc)
        self._final_new_tracks = [m['track'] for m in neue]
        for trk in getattr(self._clip.tracking, "tracks", []):
            trk.select = (trk.name in self._final_new_tracks)

    # -------------------------------------------------------------------------
    # Nicht-blockierendes Tracking (Start + Tick + Abschluss)
    # -------------------------------------------------------------------------
    def _track_start(self, context) -> None:
        """Initialisiert das tick-basierte Tracking ohne UI-Blockade."""
        scene = self._scene
        clip = self._clip
        space = self._space

        start_frame = self._start_frame
        end_frame = self._end_frame
        if end_frame < start_frame:
            end_frame = start_frame

        active_names = list(self._final_new_tracks or [])
        if not active_names:
            print("[DeepTest][Track] ⚠️ Keine aktiven Tracks.")
            return 0

        if clip and getattr(clip, "tracking", None):
            for trk in clip.tracking.tracks:
                trk.select = (trk.name in active_names)

        scene.frame_current = start_frame
        space.clip_user.frame_current = start_frame

        self._track_state = _TrackState(
            active=True,
            current=start_frame,
            end=end_frame,
            active_names=active_names,
            total_len=-1
        )
        # Gesamtanzahl speichern für Abbruchbedingung (75%-Regel)
        self._track_state.start_count = len(active_names)
        print(f"[DeepTest][Track] ▶️ Start {start_frame} → {end_frame} | {len(active_names)} Tracks aktiv")

    def _track_tick(self, context) -> bool:
        """Führt genau einen Tracking-Schritt aus. True = läuft weiter; False = abgeschlossen."""
        ts = self._track_state
        if not ts.active:
            return False

        scene = self._scene
        space = self._space
        window, area, region = self._window, self._area, self._region

        # 1) Inaktive Tracks filtern
        ts.active_names, dropped = filter_active_tracks_at_frame(context, ts.active_names, ts.current)
        if dropped > 0:
            print(f"[DeepTest][Track] {dropped} inaktive entfernt → {len(ts.active_names)} aktiv")
        if not ts.active_names:
            print(f"[DeepTest][Track] ✅ Keine aktiven Tracks mehr bei Frame {ts.current}")
            return self._track_finish(context)

        # --- Abbruchbedingung: 75% der Tracks inaktiv ---
        total_initial = getattr(ts, "start_count", len(ts.active_names))
        active_now = len(ts.active_names)
        if total_initial > 0:
            inactive_ratio = 1.0 - (active_now / total_initial)
            if inactive_ratio >= 0.75:
                print(f"[DeepTest][Track] ⏹️ 75% der Tracks inaktiv ({inactive_ratio*100:.1f}%) – Tracking beendet.")
                return self._track_finish(context)

        # 2) Formel anwenden (ShortTest-Parität)
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[DeepTest][Track] ⚠️ Formel-Fehler: {e!r}")

        # 3) Einen Frame tracken
        ok = track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
        if not ok:
            print("[DeepTest][Track] ⚠️ Tracking-Fehler – Abbruch.")
            return self._track_finish(context)

        # 4) Nächster Frame / Ende prüfen
        ts.current += 1
        if ts.current > ts.end:
            print("[DeepTest][Track] ✅ Szenenende erreicht.")
            return self._track_finish(context)

        scene.frame_current = ts.current
        space.clip_user.frame_current = ts.current
        return True

    def _track_finish(self, context) -> bool:
        """Beendet das Tracking, misst Länge und löscht die temporären Tracks."""
        ts = self._track_state
        ts.active = False
        try:
            # ----------------------------------------------------------------
            # 0) Vorab-Filterung neuer Tracks mit Threshold 30
            # ----------------------------------------------------------------
            new_tracks = getattr(self, "_final_new_tracks", [])
            clip = getattr(self, "_clip", None)
            if new_tracks:
                print(f"[DeepTest][FilterDelete] Vor Tracklängen-Messung: {len(new_tracks)} neue Tracks erkannt.")
                try:
                    filter_and_delete_tracks(
                        include_names=new_tracks,
                        threshold=30,
                        clip=clip
                    )
                    print(f"[DeepTest][FilterDelete] ✅ Filter/Delete auf neue Tracks angewendet ({len(new_tracks)} Stück).")
                except Exception as e:
                    print(f"[DeepTest][FilterDelete] ⚠️ Fehler bei Filter/Delete: {e}")
            else:
                print("[DeepTest][FilterDelete] ⚠️ Keine neuen Tracks zum Filtern gefunden.")

            # View-Layer-Sync wie ShortTest
            bpy.context.view_layer.update()
            # Formel anwenden (ShortTest-Parität)
            apply_formula_on_selected_tracks(context, max_frames=5)
            # Länge messen (nach Filterung)
            ts.total_len = int(get_total_track_length(context, start_frame=self._start_frame))
        except Exception as e:
            print(f"[DeepTest][Track] ⚠️ Messfehler: {e!r}")
            ts.total_len = 0

        print(f"[DeepTest][Track] ✅ Tracking abgeschlossen – Gesamtlänge = {ts.total_len}")

        # Playhead zurücksetzen
        reset_to_frame(context, self._start_frame)

        # Temporäre Tracks löschen
        try:
            delete_tracks_by_names(context, self._final_new_tracks)
        except Exception as e:
            print(f"[DeepTest][Track] ⚠️ Fehler beim Löschen: {e!r}")

        return False

    # -------------------------------------------------------------------------
    # Auswertung nach beendetem Tracking in derselben Threshold-Stufe
    # -------------------------------------------------------------------------
    def _evaluate_after_tracking(self, context) -> bool:
        """Bewertet die Ergebnisse der aktuellen Stufe und bereitet die nächste vor.
        Rückgabe: True = Kategorie fertig, False = nächste Stufe derselben Kategorie.
        """
        total_len = int(self._track_state.total_len if self._track_state.total_len >= 0 else 0)
        compare_len = int(self._goal_map.get(self._current_category, 0))
        print(f"[DeepTest][{self._current_category}] Track-Länge = {total_len}, Vergleich = {compare_len}")

        # ---- Bewertung (adaptive Stufenlogik) -------------------------------
        if total_len >= compare_len:
            print(f"[DeepTest][{self._current_category}] ✅ Verbesserte oder gleiche Länge ({total_len} >= {compare_len})")
            self._goal_map[self._current_category] = total_len
            self._best_thresholds[self._current_category] = self._current_value
            if self._current_category == "rot_xy":

                set_scene_props(self._scene,
                    kaiserlich_rot_thresh_x=1.0,
                    kaiserlich_rot_thresh_y=1.0)
            elif self._current_category == "scale":
                set_scene_props(self._scene,
                    kaiserlich_scale_thresh_min=1.0,
                    kaiserlich_scale_thresh_max=1.0)
            elif self._current_category in ("rot_scale_rot", "rot_scale_scale"):
                set_scene_props(self._scene,
                    kaiserlich_rot_scale_thresh_rot=1.0,
                    kaiserlich_rot_scale_thresh_scale=1.0)
            elif self._current_category == "perspective":
                set_scene_props(self._scene, kaiserlich_perspective_thresh=1.0)

            self._current_step_index += 1
            print(f"[DeepTest][Eval] ✓ Ziel erreicht | next step ({self._current_step_index})")

        else:
            # Kein Zugewinn → prüfen, ob MIN erreicht
            if self._current_value <= MIN_THRESHOLD_VAL + 1e-12:
                print(f"[DeepTest][Eval] ✗ Kein Zugewinn, MIN erreicht → nächste Stufe")
                self._current_step_index += 1
                # Basiswert unverändert lassen – nächste Stufe startet vom aktuellen Startpunkt.
            else:
                # gleiche Stufe wiederholen mit weiter abgesenktem Basiswert
                self._base_value = self._current_value
                print(f"[DeepTest][Eval] ↻ Ziel verfehlt | Wiederhole Stufe {self._current_step_index+1} mit niedrigerem Threshold")

        # Reset Playhead
        reset_to_frame(context, self._start_frame)

        # Kategorie fertig, wenn alle Reduktionsstufen durch oder MIN erreicht
        if self._current_step_index >= len(REDUCTION_STEPS):
            print(f"[DeepTest][{self._current_category}] Kategorie abgeschlossen (alle Stufen durchlaufen).")
            return True

        return False

    # ------------------------------------------------------------------------
    def _finish(self, context):
        print("\n[DeepTest] ✅ Abschluss – beste Thresholds:")
        for k, v in self._best_thresholds.items():
            print(f"  {k}: {v:.6f}")
        # Ergebnisse global in die Szene schreiben
        scene = context.scene
        scene["kaiserlich_best_thresholds"] = self._best_thresholds

        # ---- Thresholds in Szene anwenden ----
        if "rot_xy" in self._best_thresholds:
            set_scene_props(scene,
                kaiserlich_rot_thresh_x=self._best_thresholds["rot_xy"],
                kaiserlich_rot_thresh_y=self._best_thresholds["rot_xy"])
        if "scale" in self._best_thresholds:
            set_scene_props(scene,
                kaiserlich_scale_thresh_min=self._best_thresholds["scale"],
                kaiserlich_scale_thresh_max=min(1,self._best_thresholds["scale"] * 1.1))
        # rot_scale ist zweigeteilt gespeichert
        rot_val = self._best_thresholds.get("rot_scale_rot")
        scale_val = self._best_thresholds.get("rot_scale_scale")
        if rot_val or scale_val:
            set_scene_props(scene,
                kaiserlich_rot_scale_thresh_rot=(rot_val or 1.0),
                kaiserlich_rot_scale_thresh_scale=(scale_val or 1.0))
        if "perspective" in self._best_thresholds:
            set_scene_props(scene,
                kaiserlich_perspective_thresh=self._best_thresholds["perspective"])

        print("[DeepTest] 💾 Alle finalen Threshold-Werte in Szene eingetragen.")
        return self._teardown(context, cancelled=False)

    def _teardown(self, context, cancelled=False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        msg = "Deep Test abgebrochen." if cancelled else "Deep Test abgeschlossen."
        try:
            self.report({'INFO'}, msg)
        except:
            print(msg)
        return {'CANCELLED' if cancelled else 'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)

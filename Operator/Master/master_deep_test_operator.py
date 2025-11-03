# Operator/Master/master_deep_test_operator.py
import bpy
import time
import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple, Set
from bpy.types import Operator, Context

# ---- Helper-Importe ---------------------------------------------------------
from ...Helper.util_clip import get_active_clip
from ...Helper.scene import get_end_frame
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.newmarker import classify_markers
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.snapshot import snapshot_active_markers
from ...Helper.detect import detect_features
from ...Helper.cleaneup import cleanup_new_markers
from ...Helper.delete import delete_tracks_by_names
from ...Helper.track_length_helper import get_total_track_length
from ...Helper.track_markers_helper import track_markers_with_override
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.util_scene import set_scene_props
from ...Helper.init_detect_state import init_detect_state
from ...Helper.reset_helper import reset_all_thresholds
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.formula_helper import apply_formula_on_selected_tracks
from ...Helper.filter_and_delete_tracks import filter_and_delete_tracks

# ---- Frame-Cache-Import ----------------------------------------------------
from ...Helper.frame_value_cache import (
    get_frame_values,
    save_frame_values,
    apply_cached_values
)
# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_00"

# ---- Reduktions-Stufen ------------------------------------------------------
REDUCTION_STEPS = [0.05, 0.067, 0.089, 0.119, 0.158, 0.211, 0.281, 0.375, 0.499, 0.666, 0.888]
MIN_THRESHOLD_VAL = 0.00001

# ---- Interner Tracking-State (nicht-blockierend) ---------------------------
@dataclass
class _TrackState:
    active: bool = False
    current: int = 0
    end: int = 0
    active_names: List[str] = None
    total_len: int = -1  # -1 = noch nicht gemessen


class KAISERLICHTRACKER_OT_master_deep_test_operator(Operator):
    """Deep Threshold Test (Modal): führt pro Kategorie stufenweise Reduktion der Thresholds durch und testet jeweils."""
    bl_idname = "kaiserlich_tracker.master_deep_test_operator"
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

        # --- NEU: harte Deselektion aller Tracks zu Beginn -----------------
        try:
            deselected = self._deselect_all_tracks(context)
        except Exception as ex:
            print(f"[Kaiserlich Tracker][MasterDeepTest][Selection] ⚠️ Deselektion fehlgeschlagen: {ex!r}")

        self._hz, self._vc = self._clip.size
        self._ratio_xy = (self._hz / self._vc) if self._vc else 1.0
        self._ef_target = int(self._scene.kaiserlich_markers_per_frame)
        self._tolerance = max(1.0, self._ef_target * 0.10)
        self._start_frame = int(self._scene.frame_start)
        self._end_frame = int(get_end_frame(context))
        self._current_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._current_frame
        self._scene.frame_current = self._current_frame

        # --- NEU: Sicherstellen, dass mindestens 50 Frames bis Szenenende verbleiben ---
        current_frame = int(self._scene.frame_current)
        end_frame = int(get_end_frame(context))
        remaining = end_frame - current_frame

        # Ursprungsposition global sichern
        self._user_original_frame = current_frame

        if remaining < 50:
            new_start = max(self._scene.frame_start, end_frame - 50)
            self._scene.frame_current = new_start
            try:
                if self._space and getattr(self._space, "clip_user", None):
                    self._space.clip_user.frame_current = new_start
            except Exception:
                pass
        else:
            print(f"[MasterDeepTest] ✅ Ausreichend Frames ({remaining}) – keine Verschiebung erforderlich.")
        # -------------------------------------------------------------------------------
        # Thresholds global auf 1.0 zurücksetzen (ShortTest-Parität)
        try:
            reset_all_thresholds(context, active_props=[])
        except Exception as e:
            print(f"[MasterDeepTest][Init] ⚠️ Threshold-Reset fehlgeschlagen: {e!r}")
        # Detect-Parameter initialisieren (identisch zum ShortTest)
        try:
            scene = context.scene
            params = scene.get("bootstrap_params", None)

            if params:
                self._last_md = float(params.get('md', 100))
                self._margin = int(round(float(params.get('ma', 100)) * 1.1))
                self._threshold = float(params.get('tr', 0.5))
                self._pattern_size = int(params.get('pz', 50))
                self._search_size = int(params.get('sz', 100))
                self._hz = int(params.get('hz', 1))
                self._vc = int(params.get('vc', 1))
            else:
                clip = getattr(context.space_data, "clip", None)
                if clip is None:
                    raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")

                self._hz, self._vc = clip.size
                tracking_settings = getattr(clip.tracking, "settings", None)
                self._margin = getattr(tracking_settings, "margin", 100)
                self._pattern_size = getattr(tracking_settings, "pattern_size", 50)
                self._search_size = getattr(tracking_settings, "search_size", 100)
                self._last_md = self._hz * 0.025
                self._threshold = 0.0001

            # Frame-spezifisches min_distance ggf. überschreiben
            md_cache = scene.get("min_distance_values", {})
            if md_cache:
                fn = str(scene.frame_current)
                if fn in md_cache:
                    cached_md = float(md_cache[fn])
                    self._last_md = cached_md

        except Exception as ex:

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
            self.report({'INFO'}, "Keine aktiven Szenenwerte – MasterDeepTest übersprungen, starte DetectAdapt...")
        
            try:
                if hasattr(bpy.ops, "kaiserlich_tracker"):
                    bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                else:
                    print("[MasterDeepTest] ⚠️ Operatorstruktur unvollständig – Übergabe übersprungen.")
            except Exception as ex:
                print(f"[MasterDeepTest] ⚠️ Fehler bei Übergabe an master_detect_adapt: {ex!r}")
        
            return {'FINISHED'}



        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._track_state = _TrackState(active=False, current=0, end=0, active_names=[], total_len=-1)
        self._phase = "category_select"
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Helper: Alle Tracks im aktiven Clip deselektieren
    # ------------------------------------------------------------------------
    def _deselect_all_tracks(self, context: bpy.types.Context) -> int:
        """Setzt track.select = False für alle Tracks im aktiven Clip.
        Returns: Anzahl zuvor selektierter Tracks, die deselektiert wurden.
        """
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        if not tracking or not getattr(tracking, "tracks", None):
            return 0
        changed = 0
        for tr in tracking.tracks:
            if getattr(tr, "select", False):
                tr.select = False
                changed += 1
        return changed

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

        # ---- Frame-Cache prüfen --------------------------------------------
        cached = apply_cached_values(self._scene, self._scene.frame_current)
        if cached:
            self._current_step_index = len(REDUCTION_STEPS)
            return
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

        elif self._current_category == "rot_scale_scale":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=0.0,
                kaiserlich_rot_scale_thresh_scale=1.0
            )
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=1.0)

    # ------------------------------------------------------------------------
    def _process_threshold_cycle(self, context) -> bool:
        """Durchläuft die Threshold-Stufen sequentiell und prüft je Durchgang."""
        if self._current_step_index >= len(REDUCTION_STEPS):
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

        elif self._current_category == "rot_scale_scale":
            set_scene_props(
                self._scene,
                kaiserlich_rot_scale_thresh_rot=0.0,
                kaiserlich_rot_scale_thresh_scale=next_val
            )
    
        elif self._current_category == "perspective":
            set_scene_props(self._scene, kaiserlich_perspective_thresh=next_val)
        
        # ---- Detect (vollständig nach DetectAdapt-Struktur) --------------------
        ef_target = int(self._scene.kaiserlich_markers_per_frame)
        tolerance = ef_target * 0.10
        hz = self._hz
        vc = self._vc
        ma = self._margin
        tr = self._threshold
        pz = self._pattern_size
        scene = self._scene

        pre_snapshot = snapshot_active_markers(context)
        baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}

        max_loops = self._detect_loop_max
        last_md = float(self._last_md)
        cleaned_new = []

        # --- Fix: Cached min_distance übernehmen und Suche überspringen ---
        _md_cache = self._scene.get("min_distance_values", {})
        fn = str(self._scene.frame_current)
        if fn in _md_cache:
            cached_md = float(_md_cache[fn])
            self._last_md = cached_md
            last_md = cached_md
            # Nur einmalige Detection durchführen, keine iterative Anpassung
            max_loops = 1


        for loop in range(max_loops):
            detect_features(context, placement='FRAME', margin=ma, threshold=tr,
                            min_distance=int(max(1, round(last_md))))

            # Blender selektiert automatisch neue Marker → zurücksetzen
            clip = getattr(context.space_data, 'clip', None)
            if clip and getattr(clip, 'tracking', None):
                for trk in clip.tracking.tracks:
                    trk.select = False

            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)
            if len(neue_marker) > 0:
                print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
            if len(alte_marker) > 0:
                print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])           

            # Cleanup schützt alte Marker
            cleaned_new, deleted_old = cleanup_new_markers(
                context, alte_marker, neue_marker, pz=pz, hz=hz, vc=vc)
            remaining = len(cleaned_new)

            # --- Desync prüfen ---
            if clip and getattr(clip, "tracking", None):
                clip_names = {t.name for t in clip.tracking.tracks}
                synced_cleaned = [m for m in cleaned_new if m['track'] in clip_names]
                if len(synced_cleaned) != len(cleaned_new):
                    removed = [m['track'] for m in cleaned_new if m['track'] not in clip_names]
                cleaned_new = synced_cleaned
                remaining = len(cleaned_new)


            diff = remaining - ef_target
            if remaining == 0:
                print("[MasterDeepTest][DetectAdapt] ⚠️ Keine gültigen neuen Marker – neuer Versuch.")
            elif abs(diff) <= tolerance and remaining > 0:
                break
            else:
                print(f"[MasterDeepTest][DetectAdapt] Δ={diff:+.0f}, Ziel={ef_target}, Toleranz={tolerance:.1f}")

            # Adaptive min_distance-Anpassung
            if remaining == 0:
                last_md = max(2.0, last_md * 0.8)
            else:
                ratio = remaining / max(1, ef_target)
                factor = (((ratio - 1.0) / 2.0) + 1.0)
                new_md = last_md * factor
                new_md = min(max(new_md, 2.0), hz * 0.25)
                last_md = new_md

            # Cleanup für nächste Runde
            if loop < max_loops - 1:
                del_names = [m['track'] for m in cleaned_new]
                if del_names:
                    delete_tracks_by_names(context, del_names)
                time.sleep(0.05)

        self._last_md = last_md

        # Speicherung pro Frame (inkl. Interpolation)
        frame_num = scene.frame_current
        md_val = float(last_md)
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        known_list = list(md_dict.get("known_frames", []))
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = md_val

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
                    interp = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = interp

        # Nur wirklich neue Marker selektieren
        clip = getattr(context.space_data, 'clip', None)
        final_tracks = []
        if clip and getattr(clip, 'tracking', None):
            trk_list = clip.tracking.tracks
            new_tracks = [t for t in trk_list if t.name not in baseline_start_tracknames]
            for t in trk_list:
                t.select = False
            for nt in new_tracks:
                nt.select = True
                final_tracks.append(nt.name)

        self._final_new_tracks = final_tracks

        try:
            bpy.context.view_layer.update()
        except:
            pass

        # ---- Tracking starten (non-blocking) ----
        self._track_start(context)
        self._phase = "tracking_tick"
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

        # --------------------------------------------------------------------
        #  Startframe bestimmen:
        #  - Primär: erster Marker-Frame der neu erzeugten Tracks
        #  - Sekundär: aktueller Playhead
        #  - Fallback: Szenenstart
        # --------------------------------------------------------------------
        start_frame = int(scene.frame_start)
        try:
            tracking = getattr(clip, "tracking", None)
            new_tracks = getattr(self, "_final_new_tracks", [])
            if tracking and new_tracks:
                marker_frames = []
                for name in new_tracks:
                    tr = tracking.tracks.get(name)
                    if tr and tr.markers:
                        marker_frames.append(tr.markers[0].frame)
                if marker_frames:
                    start_frame = min(marker_frames)
            else:
                # Kein expliziter neuer Track bekannt → aktuellen Frame verwenden
                start_frame = int(scene.frame_current)
        except Exception as ex:
            start_frame = int(scene.frame_current or scene.frame_start)

        # Playhead auf den Startframe setzen (visuell synchronisieren)
        reset_to_frame(context, start_frame)
        end_frame = self._end_frame
        if end_frame < start_frame:
            end_frame = start_frame

        active_names = list(self._final_new_tracks or [])
        if not active_names:
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
        # Startframe im State speichern für späteren Reset
        self._track_state.start_frame = start_frame
        # Gesamtanzahl speichern für Abbruchbedingung (75%-Regel)
        self._track_state.start_count = len(active_names)

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
        if not ts.active_names:
            return self._track_finish(context)

        # --- Neue Abbruchbedingungen basierend auf UI-Property "Frames per Track" ---
        frames_per_track = int(scene.kaiserlich_frames_per_track) * 2
        current_frame_index = ts.current - getattr(ts, "start_frame", scene.frame_start)

        # 1. Wenn die gewünschte Frameanzahl pro Track erreicht ist
        if current_frame_index >= frames_per_track:
            return self._track_finish(context)

        # 2. Wenn keine aktiven Tracks mehr vorhanden sind
        if len(ts.active_names) == 0:
            return self._track_finish(context)

        # 3. Wenn das Szenenende erreicht oder überschritten wurde
        if ts.current >= ts.end:
            return self._track_finish(context)

        # 2) Formel anwenden (ShortTest-Parität)
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[MasterDeepTest][Track] ⚠️ Formel-Fehler: {e!r}")

        # 3) Einen Frame tracken
        ok = track_markers_with_override(window, area, region, space, backwards=False, sequence=False)
        if not ok:
            return self._track_finish(context)

        # 4) Nächster Frame / Ende prüfen
        ts.current += 1
        if ts.current > ts.end:
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
                try:
                    filter_and_delete_tracks(
                        include_names=new_tracks,
                        threshold=30,
                        clip=clip
                    )
                except Exception as e:
                    print(f"[MasterDeepTest][FilterDelete] ⚠️ Fehler bei Filter/Delete: {e}")
            else:
                print("[MasterDeepTest][FilterDelete] ⚠️ Keine neuen Tracks zum Filtern gefunden.")

            # View-Layer-Sync wie ShortTest
            bpy.context.view_layer.update()
            # Formel anwenden (ShortTest-Parität)
            apply_formula_on_selected_tracks(context, max_frames=5)
            # Länge messen (nach Filterung, nur neue Tracks berücksichtigen)
            ts.total_len = int(
                get_total_track_length(
                    context,
                    start_frame=self._start_frame,
                    include_names=getattr(self, "_final_new_tracks", []),
                )
            )
        except Exception as e:
            ts.total_len = 0


        # Nach jedem Track-Durchgang soll der Playhead auf den ursprünglichen Startframe zurückspringen
        try:
            start_f = int(getattr(self._track_state, "start_frame", self._start_frame))
            reset_to_frame(context, start_f)
        except Exception as ex:
            print(f"[MasterDeepTest][Track] ⚠️ Fehler beim Playhead-Reset (Startframe): {ex!r}")

        # Temporäre Tracks löschen
        try:
            delete_tracks_by_names(context, self._final_new_tracks)
        except Exception as e:
            print(f"[MasterDeepTest][Track] ⚠️ Fehler beim Löschen: {e!r}")

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

        # ---- Bewertung (adaptive Stufenlogik) -------------------------------
        if total_len >= compare_len:
            self._goal_map[self._current_category] = total_len
            self._best_thresholds[self._current_category] = self._current_value

            # ---- Frame-Werte im Cache speichern ----------------------------
            frame_values = {self._current_category: self._current_value}
            save_frame_values(self._scene, self._scene.frame_current, frame_values)
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

        else:
            # Kein Zugewinn → prüfen, ob MIN erreicht
            if self._current_value <= MIN_THRESHOLD_VAL + 1e-12:
                # --- NEU: Zähler für aufeinanderfolgende MIN-Erreichungen ---
                if not hasattr(self, "_min_reach_count"):
                    self._min_reach_count = 0

                self._min_reach_count += 1

                # Wenn dreimal hintereinander erreicht, Kategorie beenden
                if self._min_reach_count >= 3:
                    self._current_step_index = len(REDUCTION_STEPS)
                    self._min_reach_count = 0
                    return True

                # ansonsten zur nächsten Stufe springen
                self._current_step_index += 1
                # Wichtig: Basis auf 1.0 zurücksetzen, damit die nächste Stufe
                # exakt dem definierten REDUCTION_STEPS-Faktor entspricht.
                self._base_value = 1.0

            else:
                # Bei Zielverfehlung ohne MIN: nicht in derselben Stufe „heruntermultiplizieren“,
                # sondern zur nächsten REDUCTION_STEPS-Stufe wechseln.
                if hasattr(self, "_min_reach_count"):
                    self._min_reach_count = 0
                self._current_step_index += 1
                # Basiswert zurücksetzen, damit next_val = 1.0 * REDUCTION_STEPS[idx]
                self._base_value = 1.0   

        # --------------------------------------------------------------------
        # Kein Rücksprung auf Szenenanfang mehr:
        # Nach jeder Auswertung bleibt der Playhead am letzten Tracking-Start.
        # Dieser Frame wird als Startpunkt für den nächsten Detect-Cycle verwendet.
        # --------------------------------------------------------------------
        try:
            start_f = int(getattr(self._track_state, "start_frame", self._start_frame))
            reset_to_frame(context, start_f)
        except Exception as ex:
            print(f"[MasterDeepTest][Eval] ⚠️ Fehler beim Playhead-Reset (Eval): {ex!r}")

        # Kategorie fertig, wenn alle Reduktionsstufen durch oder MIN erreicht
        # ---------------------------------------------------------------
        # 🔁 Thresholds für nächste Kategorie immer auf 1.0 zurücksetzen
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

        if self._current_step_index >= len(REDUCTION_STEPS):
            return True

        return False

    # ------------------------------------------------------------------------
    def _finish(self, context):
        for k, v in self._best_thresholds.items():
            print(f"  {k}: {v:.6f}")
        # Ergebnisse global in die Szene schreiben
        scene = context.scene
        scene["kaiserlich_best_thresholds"] = self._best_thresholds

        # ---- Thresholds in Szene anwenden ----
        if "rot_xy" in self._best_thresholds:
            best_x = self._best_thresholds["rot_xy"]
            best_y = min(1.0, best_x * (self._hz / self._vc))
            set_scene_props(scene,
                kaiserlich_rot_thresh_x=best_x,
                kaiserlich_rot_thresh_y=best_y)

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

        # --- NEU: Playhead nach Test wiederherstellen -----------------------
        try:
            restore_frame = getattr(self, "_user_original_frame", None)
            if restore_frame is not None:
                self._scene.frame_current = int(restore_frame)
                if self._space and getattr(self._space, "clip_user", None):
                    self._space.clip_user.frame_current = int(restore_frame)
        except Exception as ex:
            print(f"[MasterDeepTest] ⚠️ Fehler beim Wiederherstellen des Playheads: {ex!r}")
        # -------------------------------------------------------------------

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
        # --- NEU: Globale Wiederherstellung der ursprünglichen Playhead-Position ---
        try:
            restore_frame = getattr(self, "_user_original_frame", None)
            if restore_frame is not None:
                self._scene.frame_current = int(restore_frame)
                if self._space and getattr(self._space, "clip_user", None):
                    self._space.clip_user.frame_current = int(restore_frame)
        except Exception as ex:
            print(f"[MasterDeepTest] ⚠️ Fehler bei globaler Wiederherstellung: {ex!r}")
        # ---------------------------------------------------------------------------
        # ---------------------------------------------------------------------------
        # 🔁 NACH ABSCHLUSS: Weitergabe an Master Detect Adapt Operator
        # ---------------------------------------------------------------------------
        if not cancelled:
            try:
                # Sicherstellen, dass aktuelle Kontextdaten vollständig sind
                if context and hasattr(bpy.ops, "kaiserlich_tracker"):
                    result = bpy.ops.kaiserlich_tracker.master_detect_adapt('INVOKE_DEFAULT')
                else:
                    print("[MasterDeepTest] ⚠️ Kontext oder Operatorstruktur unvollständig – Übergabe übersprungen.")
            except Exception as ex:
                print(f"[MasterDeepTest] ⚠️ Fehler bei Übergabe an master_detect_adapt: {ex!r}")

        # Rückgabestatus wie gewohnt
        return {'CANCELLED' if cancelled else 'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_deep_test_operator)

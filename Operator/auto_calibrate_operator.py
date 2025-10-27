# Operator/auto_calibrate_operator.py
import bpy
import time
from typing import Any, Dict, List, Optional, Tuple, Set

# --- Zulässige, generische Helper (KEIN shorttest/deeptest Import!) ----------
from ..Helper.util_format import fmt8
from ..Helper.util_thresholds import set_all_thresholds_to_one
from ..Helper.util_scene import set_scene_props, call_get_start_frame
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers

# -------------------------- Scene Keys (lokal) -------------------------------
SCENE_TOTAL_TRACK_LEN_BASE = "kaiserlich_len_base_total"
SCENE_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_STEP2 = "kaiserlich_len_scale_00"
SCENE_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_STEP4 = "kaiserlich_len_perspective_0"

SCENE_BEST_ROTXY = "kaiserlich_best_rot_xy"              # (rx, ry, score)
SCENE_BEST_SCALE = "kaiserlich_best_scale"                # (smin, smax, score)
SCENE_BEST_ROT_SCALE = "kaiserlich_best_rot_scale"        # (rth, sth, score)
SCENE_BEST_PERSPECTIVE = "kaiserlich_best_perspective"    # (pth, score)


# ------------------------ Bootstrap (Master/Fallback) ------------------------
def _bootstrap_params(context, scene, ef_target: int):
    import math
    params = scene.get("bootstrap_params", None)
    if params:
        md = float(params.get('md', 100.0))
        try:
            ma = int(params.get('ma', 30))
        except Exception:
            ma = 30
        ma = int(round(ma * 1.1))
        tr = float(params.get('tr', 0.5))
        pz = int(params.get('pz', 50))
        sz = int(params.get('sz', 0))
        hz = int(params.get('hz', 1))
        vc = bool(params.get('vc', False))
        za = max(1, int(ef_target) * 4)
        og = int(math.ceil(za * 1.1))
        ug = int(math.floor(za * 0.9))
        frame_end = getattr(scene, "frame_end", None)
        return md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, "master"

    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")

    hz = int(clip.size[0])
    vc = int(clip.size[1])
    frame_end = getattr(scene, "frame_end", None)

    tracking_settings = getattr(clip, "tracking", None)
    tracking_settings = getattr(tracking_settings, "settings", None)
    ma = int(getattr(tracking_settings, "margin", 100) if tracking_settings else 100)
    pz = int(getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50)
    sz = int(getattr(tracking_settings, "search_size", 100) if tracking_settings else 100)

    md = float(hz) * 0.025
    tr = 0.0001
    import math
    za = max(1, int(ef_target) * 4)
    og = int(math.ceil(za * 1.1))
    ug = int(math.floor(za * 0.9))

    print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
          f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
          f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")
    return md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, "fallback"


# -----------------------------------------------------------------------------
#  MODAL AUTO-CALIBRATE (ShortTest + Deep im Operator selbst)
# -----------------------------------------------------------------------------
class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Automatische Kalibrierung: Kurztest je Paar/Einzelwert → bei Verbesserung Langtest.
       Alles direkt im Operator (keine shorttest/deeptest-Helper). Live-UI."""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate (Modal, Inline, Self-Contained)"
    bl_options = {"REGISTER", "INTERNAL"}

    tracks_to_delete: bpy.props.StringProperty(
        name="Tracks to delete (comma-separated)",
        default="",
        description="Optional: Namen der zu löschenden Tracks (Komma-getrennt)"
    )

    # ---- Runtime State ------------------------------------------------------
    _timer = None
    _budget_ms: float = 12.0
    _phase: str = "INIT"
    _scene = None
    _clip = None
    _window = _area = _region = _space = None

    # Detect-Adapt State
    _hz = 0
    _vc = 0
    _ma = 100
    _pz = 50
    _sz = 100
    _ef_target = 25
    _md = 0.0
    _tr = 0.0001
    _loop = 0
    _max_loops = 8
    _baseline_start_names: Set[str] = set()
    _pre_snapshot = None
    _last_detect_new: List[Dict[str, Any]] = []
    _last_deleted_old: int = 0
    _og = 0
    _ug = 0

    # Tracking-State
    _start_frame: int = 0
    _end_frame: int = 0
    _cur_frame: int = 0
    _original_selected: List[str] = []
    _frames_processed: int = 0
    _max_frames: int = 0  # 0 = kein Limit

    # Eval/Deep Pipeline
    _eval_step_index: int = 0       # 0..3 → STEP1..STEP4
    _eval_frames_short: int = 25    # Kurztest pro Kandidat
    _eval_frames_long: int = 0      # 0 = bis Ende/Stopkriterien
    _base_len: int = 0
    _step_vals: Dict[str, float] = {}

    # ------------------------------------------------------------
    def _r(self, msg: str):
        try:
            self.report({'INFO'}, msg)
        except Exception:
            pass
        print(msg)

    # ------------------------------------------------------------
    def execute(self, context):
        self._scene = context.scene
        self._clip = getattr(context.space_data, "clip", None)
        if not self._clip:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        set_all_thresholds_to_one(context)
        self._r("[AutoCalibrate] Thresholds auf 1.0 gesetzt.")

        self._phase = "DA_INIT"
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._r("[AutoCalibrate] Modal gestartet.")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------
    def cancel(self, context):
        self._cleanup(context, cancelled=True)

    # ------------------------------------------------------------
    def modal(self, context, event):
        if event.type == 'ESC':
            self._cleanup(context, cancelled=True)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        t0 = time.perf_counter()
        progressed = False
        try:
            while (time.perf_counter() - t0) * 1000.0 < self._budget_ms:
                if self._phase == "DA_INIT":
                    self._da_init(context); progressed = True; continue
                if self._phase == "DA_DETECT":
                    self._da_detect(context); progressed = True; continue
                if self._phase == "DA_CLASS":
                    self._da_classify_cleanup(context); progressed = True; continue
                if self._phase == "DA_DECIDE":
                    if self._da_decide_next(context):
                        progressed = True; continue
                    else:
                        self._phase = "TRACK_INIT"; progressed = True; continue
                if self._phase == "TRACK_INIT":
                    self._track_init(context); progressed = True; continue
                if self._phase == "TRACK_FRAME":
                    if not self._track_one_frame(context):
                        # Nach dem ersten (Basis-)Tracking → Evaluationsphase (4 Kurztests)
                        self._phase = "EVAL_INIT"
                    progressed = True; continue
                if self._phase == "EVAL_INIT":
                    self._eval_prepare(context); progressed = True; continue
                if self._phase == "EVAL_SHORT":
                    # pro STEP ein Kurztest; falls Verbesserung → direkt Langtest
                    if not self._eval_short_tick(context):
                        # noch nicht fertig -> weiter in diesem State
                        progressed = True; continue
                    else:
                        # alle STEPs evaluiert → DONE
                        self._phase = "DONE"; progressed = True; continue
                if self._phase == "DEEP_LONG_INIT":
                    self._deep_long_init(context); progressed = True; continue
                if self._phase == "DEEP_LONG_TRACK":
                    if not self._deep_long_track_tick(context):
                        progressed = True; continue
                    else:
                        # Longtest abgeschlossen → zurück zu EVAL_SHORT (nächster STEP)
                        self._phase = "EVAL_SHORT"; progressed = True; continue
                if self._phase == "DONE":
                    self._finish(context)
                    return {'FINISHED'}
                break

            if progressed:
                try:
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                except:
                    pass
            return {'RUNNING_MODAL'}

        except Exception as e:
            self.report({'ERROR'}, f"[AutoCalibrate] Fehler: {e}")
            self._cleanup(context, cancelled=True)
            return {'CANCELLED'}

    # ===================== Detect-Adapt (Basislauf) ===========================
    def _da_init(self, context):
        scene = self._scene
        self._ef_target = int(getattr(scene, "kaiserlich_markers_per_frame", 25) or 25)
        md, ma, tr, pz, sz, hz, vc, og, ug, frame_end, source = _bootstrap_params(context, scene, self._ef_target)
        self._hz, self._vc = hz, vc
        self._ma, self._pz, self._sz = int(ma), int(pz), int(sz)
        self._md, self._tr = float(md), float(tr)
        self._og, self._ug = int(og), int(ug)
        self._r(f"[ShortTest][Bootstrap:{source}] ef_target={self._ef_target} "
                f"hz={self._hz} vc={self._vc} margin={self._ma} "
                f"md={fmt8(self._md)} pz={self._pz} sz={self._sz} tr={self._tr} "
                f"og={self._og} ug={self._ug} frame_end={frame_end}")
        self._baseline_start_names = {t.name for t in self._clip.tracking.tracks}
        self._pre_snapshot = snapshot_active_markers(context)
        self._loop = 0
        self._max_loops = 8
        self._phase = "DA_DETECT"

    def _da_detect(self, context):
        self._loop += 1
        self._r(f"[ShortTest][Detect] LOOP={self._loop} md={fmt8(self._md)}")
        detect_features(context, placement='FRAME', margin=self._ma,
                        threshold=self._tr, min_distance=int(max(1, round(self._md))))
        for trk in self._clip.tracking.tracks:
            trk.select = False
        self._phase = "DA_CLASS"

    def _da_classify_cleanup(self, context):
        post = snapshot_active_markers(context)
        alte, neue = classify_markers(self._pre_snapshot, post)
        cleaned_new, deleted_old = cleanup_new_markers(context, alte, neue, pz=self._pz, hz=self._hz, vc=self._vc)
        self._last_detect_new = cleaned_new
        self._last_deleted_old = deleted_old
        self._r(f"[ShortTest][Cleanup] new={len(cleaned_new)} del_old={deleted_old}")
        self._phase = "DA_DECIDE"

    def _da_decide_next(self, context) -> bool:
        remaining = len(self._last_detect_new)
        diff = remaining - self._ef_target
        tolerance = max(1, int(self._ef_target * 0.10))
        if abs(diff) <= tolerance:
            self._r(f"[ShortTest] Ziel erreicht ({remaining}/{self._ef_target})")
            for trk in self._clip.tracking.tracks:
                trk.select = (trk.name not in self._baseline_start_names)
            return False
        if remaining > 0:
            ratio = self._ef_target / remaining
            factor = max(0.5, min(2.0, ratio))
            self._md = max(1.0, self._md / factor)
        else:
            self._md *= 1.5
            self._r("[ShortTest] Keine neuen Marker → erhöhe min_distance.")
        if self._loop < self._max_loops:
            try:
                delete_tracks_by_names(context, [m['track'] for m in self._last_detect_new])
            except Exception:
                pass
        if self._loop >= self._max_loops:
            self._r("[ShortTest] Max Loops erreicht.")
            for trk in self._clip.tracking.tracks:
                trk.select = (trk.name not in self._baseline_start_names)
            return False
        self._phase = "DA_DETECT"
        return True

    # ===================== Frameweises Tracking (Allgemein) ===================
    def _track_init(self, context):
        self._r("[InlineTrack] ▶ Start")
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")
        self._start_frame = int(call_get_start_frame(context))
        self._end_frame = int(getattr(self._scene, "frame_end", self._start_frame))
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            raise RuntimeError("Keine Tracks selektiert (InlineTrack).")
        for tr in self._clip.tracking.tracks:
            tr.select = (tr.name in self._original_selected)
        self._cur_frame = max(self._start_frame, int(self._scene.frame_current))
        self._space.clip_user.frame_current = self._cur_frame
        self._scene.frame_current = self._cur_frame
        self._frames_processed = 0
        self._max_frames = int(getattr(self._scene, "kaiserlich_max_frames", 0) or 0)
        self._phase = "TRACK_FRAME"

    def _track_one_frame(self, context) -> bool:
        try:
            apply_formula_on_selected_tracks(context, max_frames=5)
        except Exception as e:
            print(f"[InlineTrack] ⚠️ Formel-Fehler: {e}")
        ok = track_markers_with_override(self._window, self._area, self._region, self._space,
                                         backwards=False, sequence=False)
        if not ok:
            self._r("[InlineTrack] ⚠️ Tracking-Fehler, Abbruch.")
            return False
        self._frames_processed += 1
        if self._space.clip_user.frame_current == self._cur_frame:
            self._space.clip_user.frame_current += 1
        if self._space.clip_user.frame_current > self._end_frame:
            self._space.clip_user.frame_current = self._end_frame
        self._scene.frame_current = self._space.clip_user.frame_current
        self._cur_frame = self._space.clip_user.frame_current
        processing_names, _ = filter_active_tracks_at_frame(context, self._original_selected, self._cur_frame)
        if self._cur_frame >= self._end_frame:
            self._r("[InlineTrack] ✅ Szenenende erreicht.")
            return False
        if not processing_names:
            self._r("[InlineTrack] ✅ Keine aktiven Tracks mehr.")
            return False
        if self._max_frames > 0 and self._frames_processed >= self._max_frames:
            self._r("[InlineTrack] ⚠️ Sicherheitslimit erreicht.")
            return False
        return True

    # ===================== Kurztest/Deep im Operator ==========================
    def _measure_total_track_length(self, only_selected=True) -> int:
        """Approx: Summiere Marker-Anzahl je (selektiertem) Track."""
        total = 0
        for tr in self._clip.tracking.tracks:
            if only_selected and not tr.select:
                continue
            try:
                total += len(tr.markers)
            except Exception:
                pass
        return int(total)

    def _clear_new_tracks_since(self, baseline_names: Set[str]):
        kill = [t.name for t in self._clip.tracking.tracks if t.name not in baseline_names]
        if kill:
            delete_tracks_by_names(bpy.context, kill)

    def _eval_prepare(self, context):
        """Initialer Basiswert & Plan für STEP1..STEP4."""
        # Basis-Messung aus dem vorigen Lauf: Länge schreiben
        base_len = self._measure_total_track_length(only_selected=True)
        self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = int(base_len)
        self._base_len = int(base_len)
        self._r(f"[Eval] Base length (selektiert): {self._base_len}")

        # Eval-Parameter
        self._eval_step_index = 0
        self._eval_frames_short = int(getattr(self._scene, "kaiserlich_eval_frames_short", 25) or 25)
        self._eval_frames_long = int(getattr(self._scene, "kaiserlich_eval_frames_long", 0) or 0)  # 0 = voll

        # Platz für Step-Ergebnisse
        self._step_vals = {SCENE_STEP1: 0.0, SCENE_STEP2: 0.0, SCENE_STEP3: 0.0, SCENE_STEP4: 0.0}

        # Marker-Baseline merken (um zwischen den Tests aufzuräumen)
        self._eval_baseline_names = {t.name for t in self._clip.tracking.tracks}

        self._phase = "EVAL_SHORT"

    def _eval_short_tick(self, context) -> bool:
        """
        Führt sequentiell STEP1..STEP4 aus (Kurztest je Paar/Einzelwert).
        Bei Verbesserung (>= Base) startet unmittelbar der Langtest.
        Return: True → alle vier STEPs abgearbeitet
        """
        steps = (("STEP1", SCENE_STEP1), ("STEP2", SCENE_STEP2),
                 ("STEP3", SCENE_STEP3), ("STEP4", SCENE_STEP4))
        if self._eval_step_index >= len(steps):
            self._r("[Eval] Alle STEPs abgeschlossen.")
            return True

        step_name, scene_key = steps[self._eval_step_index]

        # 1) Kurztest für diesen STEP: begrenzte Frames
        improved, measured = self._run_short_for_step(context, step_name, self._eval_frames_short)
        self._scene[scene_key] = float(measured)
        self._r(f"[Eval][{step_name}] short={measured} (base={self._base_len}) "
                f"{'→ Verbesserung' if improved else '→ keine Verbesserung'}")

        # 2) Falls Verbesserung: Langtest initialisieren
        if improved:
            self._pending_deep_step = step_name
            self._pending_deep_best = None  # (params_dict, score)
            self._phase = "DEEP_LONG_INIT"
            return False

        # 3) Kein Deep → zum nächsten STEP
        self._eval_step_index += 1
        # Aufräumen zwischen Tests (neue Tracks entfernen)
        self._clear_new_tracks_since(self._eval_baseline_names)
        return False

    # ---------------- SHORTTEST je STEP (intern) ----------------
    def _run_short_for_step(self, context, step_name: str, max_frames: int) -> Tuple[bool, int]:
        """
        Führt einen verkürzten Detect-Adapt + Tracking durch (bis max_frames),
        in einem isolierten Kontext für genau diesen STEP.
        Heuristik: wir variieren nur die relevanten Thresholds minimal (neutral = Scene-Props).
        """
        # a) Setup: aktuelle Scene-Props merken (für STEP-spez. Variation möglich)
        scene = self._scene

        # b) Detect-Adapt (kurz): separate MinDistance-Start (sanft)
        baseline = {t.name for t in self._clip.tracking.tracks}
        pre = snapshot_active_markers(context)
        md = max(1.0, float(self._hz) * 0.02)  # sanfter als Basis
        tr = self._tr
        loops = 0
        target = max(1, int(getattr(scene, "kaiserlich_markers_per_frame", 25) or 25))
        while loops < 4:  # kurz halten
            loops += 1
            detect_features(context, placement='FRAME', margin=self._ma,
                            threshold=tr, min_distance=int(max(1, round(md))))
            for trk in self._clip.tracking.tracks:
                trk.select = False
            post = snapshot_active_markers(context)
            alte, neue = classify_markers(pre, post)
            cleaned_new, _ = cleanup_new_markers(context, alte, neue, pz=self._pz, hz=self._hz, vc=self._vc)
            if abs(len(cleaned_new) - target) <= max(1, int(target*0.1)):
                break
            if len(cleaned_new) > 0:
                ratio = target / len(cleaned_new)
                fac = max(0.5, min(2.0, ratio))
                md = max(1.0, md / fac)
            else:
                md *= 1.5
            # Clean new for next try
            delete_tracks_by_names(context, [m['track'] for m in cleaned_new])

        # c) Selektiere neue Marker (alles, was nicht baseline war)
        for trk in self._clip.tracking.tracks:
            trk.select = (trk.name not in baseline)

        # d) Tracking (begrenzte Frames)
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            raise RuntimeError("Keine CLIP_EDITOR Area (Eval Short).")
        start_frame = int(call_get_start_frame(context))
        end_frame = int(getattr(scene, "frame_end", start_frame))
        if end_frame < start_frame:
            end_frame = start_frame

        original_selected = [t.name for t in self._clip.tracking.tracks if t.select]
        self._space.clip_user.frame_current = max(start_frame, int(scene.frame_current))
        self._scene.frame_current = self._space.clip_user.frame_current

        frames_done = 0
        while frames_done < max_frames:
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[Eval Short] Formel-Fehler: {e}")
            ok = track_markers_with_override(self._window, self._area, self._region, self._space,
                                             backwards=False, sequence=False)
            if not ok:
                break
            frames_done += 1
            # advance frame
            if self._space.clip_user.frame_current < end_frame:
                self._space.clip_user.frame_current += 1
            self._scene.frame_current = self._space.clip_user.frame_current
            # early stop if no active
            names, _ = filter_active_tracks_at_frame(context, original_selected, self._scene.frame_current)
            if not names:
                break

        # e) Metrik
        score = self._measure_total_track_length(only_selected=True)

        # f) Cleanup & Restore
        for tr in self._clip.tracking.tracks:
            tr.select = (tr.name in original_selected)
        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[Eval Short] Reset-Fehler: {e}")
        # neue Tracks wieder entfernen (Isolation)
        self._clear_new_tracks_since(baseline)

        improved = (score >= int(self._base_len))
        return improved, int(score)

    # ---------------- DEEP/LANGTEST pro STEP (intern) --------------
    def _deep_long_init(self, context):
        """Starte Langtest für den zuvor verbesserten STEP: kleiner Raster-Scan → Bestwerte, dann Long-Tracking."""
        step = getattr(self, "_pending_deep_step", None)
        if not step:
            self._phase = "EVAL_SHORT"
            return
        self._r(f"[Deep] Init für {step}")

        # Kandidaten definieren (Faktorenraster)
        self._deep_candidates = []
        if step == "STEP1":  # RotXY
            rx0 = float(getattr(self._scene, "kaiserlich_rot_thresh_x", 1.0) or 1.0)
            ry0 = float(getattr(self._scene, "kaiserlich_rot_thresh_y", 1.0) or 1.0)
            factors = [0.5, 0.75, 1.0, 1.25, 1.5]
            for fx in factors:
                for fy in factors:
                    self._deep_candidates.append({"rx": rx0*fx, "ry": ry0*fy})
        elif step == "STEP2":  # Scale min/max
            smin0 = float(getattr(self._scene, "kaiserlich_scale_thresh_min", 1.0) or 1.0)
            smax0 = float(getattr(self._scene, "kaiserlich_scale_thresh_max", 1.0) or 1.0)
            factors = [0.8, 1.0, 1.2, 1.4]
            for f1 in factors:
                for f2 in factors:
                    self._deep_candidates.append({"smin": smin0*f1, "smax": smax0*f2})
        elif step == "STEP3":  # Rot+Scale Pair
            rr0 = float(getattr(self._scene, "kaiserlich_rot_scale_thresh_rot", 1.0) or 1.0)
            ss0 = float(getattr(self._scene, "kaiserlich_rot_scale_thresh_scale", 1.0) or 1.0)
            factors = [0.75, 1.0, 1.25]
            for f1 in factors:
                for f2 in factors:
                    self._deep_candidates.append({"rth": rr0*f1, "sth": ss0*f2})
        elif step == "STEP4":  # Perspective
            p0 = float(getattr(self._scene, "kaiserlich_perspective_thresh", 1.0) or 1.0)
            factors = [0.5, 0.75, 1.0, 1.25, 1.5]
            for f in factors:
                self._deep_candidates.append({"pth": p0*f})
        else:
            self._phase = "EVAL_SHORT"
            return

        self._deep_idx = 0
        self._deep_best = {"params": None, "score": -1}
        self._phase = "DEEP_LONG_TRACK"

        # Longtest-Tracking wird für jeden Kandidaten kurz (eval_frames_short) geprüft,
        # bester Kandidat -> am Ende ein längerer Validationslauf (eval_frames_long=0 => voll).

    def _apply_candidate_params(self, params: Dict[str, float]):
        # Setze Scene-Props für den jeweiligen Kandidaten
        if "rx" in params and "ry" in params:
            set_scene_props(self._scene,
                kaiserlich_rot_thresh_x=float(params["rx"]),
                kaiserlich_rot_thresh_y=float(params["ry"]))
        if "smin" in params and "smax" in params:
            set_scene_props(self._scene,
                kaiserlich_scale_thresh_min=float(params["smin"]),
                kaiserlich_scale_thresh_max=float(params["smax"]))
        if "rth" in params and "sth" in params:
            set_scene_props(self._scene,
                kaiserlich_rot_scale_thresh_rot=float(params["rth"]),
                kaiserlich_rot_scale_thresh_scale=float(params["sth"]))
        if "pth" in params:
            set_scene_props(self._scene, kaiserlich_perspective_thresh=float(params["pth"]))

    def _deep_long_track_tick(self, context) -> bool:
        """Iteriere Kandidaten: kurzer Check → bestes Set merken; am Ende optional längerer Lauf."""
        step = getattr(self, "_pending_deep_step", None)
        # a) Kandidaten im Kurzlauf
        if self._deep_idx < len(self._deep_candidates):
            params = self._deep_candidates[self._deep_idx]
            self._deep_idx += 1

            self._apply_candidate_params(params)
            self._r(f"[Deep][{step}] Probe {self._deep_idx}/{len(self._deep_candidates)} → {params}")

            improved, score = self._run_short_for_step(context, step, self._eval_frames_short)
            if score > self._deep_best["score"]:
                self._deep_best = {"params": params, "score": score}
            # UI Atem
            return False  # weiter in diesem State

        # b) Nach Kandidaten: bestes Set anwenden und (optional) längeren Validationslauf
        best = self._deep_best
        if best["params"]:
            self._apply_candidate_params(best["params"])
            self._r(f"[Deep][{step}] Best params = {best['params']} | score={best['score']}")
            # Persistiere Bestwerte in Szene
            if step == "STEP1":
                self._scene[SCENE_BEST_ROTXY] = (float(best['params']['rx']), float(best['params']['ry']), int(best['score']))
            elif step == "STEP2":
                self._scene[SCENE_BEST_SCALE] = (float(best['params']['smin']), float(best['params']['smax']), int(best['score']))
            elif step == "STEP3":
                self._scene[SCENE_BEST_ROT_SCALE] = (float(best['params']['rth']), float(best['params']['sth']), int(best['score']))
            elif step == "STEP4":
                self._scene[SCENE_BEST_PERSPECTIVE] = (float(best['params']['pth']), int(best['score']))

            # Langer Validationslauf?
            if self._eval_frames_long == 0:
                # Voller Inline-Track vom aktuellen Zustand (Detect-Adapt neu anstoßen)
                self._r(f"[Deep][{step}] Starte langen Validationslauf.")
                # Frische Marker:
                self._da_init(context)   # bootstrap neu
                # Wir springen direkt zu Detect/Track. Nach Abschluss landen wir wieder in EVAL_SHORT.
                self._phase = "DA_DETECT"
                # Nach dem langen Lauf setze Eval-Index auf next step:
                self._eval_step_index += 1
                # Base aktualisieren (der lange Lauf könnte bessere Basis schaffen)
                # Wird nach DA/Track automatisch erneut gemessen in _eval_prepare
                return True  # signalisiert: Longlauf initiiert → verlasse diesen State
            else:
                # Optionaler lang(er) Kurzlauf (N Frames)
                improved, score = self._run_short_for_step(context, step, self._eval_frames_long)
                self._r(f"[Deep][{step}] Long validation: score={score}")

        # c) zurück zum EVAL_SHORT für den nächsten STEP
        self._eval_step_index += 1
        self._phase = "EVAL_SHORT"
        return True

    # ===================== Abschluss & Cleanup ===================
    def _finish(self, context):
        # Ursprungs-Selektion wiederherstellen (so gut möglich)
        for tr in self._clip.tracking.tracks:
            tr.select = tr.select  # no-op; optional könnte man gespeicherte Selektion restoren
        self._r("[AutoCalibrate] Erfolgreich abgeschlossen.")
        self._cleanup(context, cancelled=False)

    def _cleanup(self, context, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._phase = "DONE"
        self._r("[AutoCalibrate] Abgebrochen." if cancelled else "[AutoCalibrate] Ende.")


# -----------------------------------------------------------------------------
def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_auto_calibrate)

def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_auto_calibrate)

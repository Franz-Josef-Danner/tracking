# deep_test_operator.py
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

# ---- Szenen-Keys ------------------------------------------------------------
SCENE_TOTAL_TRACK_LEN_BASE  = "kaiserlich_len_baseline_00"
SCENE_TOTAL_TRACK_LEN_STEP1 = "kaiserlich_len_rot_xy_00"
SCENE_TOTAL_TRACK_LEN_STEP2 = "kaiserlich_len_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP3 = "kaiserlich_len_rot_scale_00"
SCENE_TOTAL_TRACK_LEN_STEP4 = "kaiserlich_len_perspective_0"


# ============================================================================
#  MODALER DEEP-TEST-OPERATOR (DetectAdapt-Logik + modales Tracking)
# ============================================================================

class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Deep-Threshold-Test mit adaptiver Marker-Erkennung (identisch zu DetectAdapt)
    und nachgelagertem, modalem Frame-by-Frame-Tracking."""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------------
    #  interne Zustände / Felder
    # ------------------------------------------------------------------------
    _timer = None
    _phase = "detect"          # detect -> track -> evaluate/finish
    _scene: Optional[bpy.types.Scene] = None
    _clip: Optional[bpy.types.MovieClip] = None

    _window = None
    _area = None
    _region = None
    _space = None

    # Clip/Tracking-Parameter
    _hz = 0
    _vc = 0
    _ma = 100
    _pz = 50
    _sz = 100
    _tr = 0.0001

    # Zielwerte aus UI
    _ef_target = 25
    _tolerance = 0

    # DetectAdapt-Status
    _detect_loop = 0
    _detect_loop_max = 8
    _pre_snapshot: List[Dict[str, Any]] = []
    _baseline_start_tracknames: Set[str] = set()
    _last_md: float = 100.0
    _deleted_old_count: int = 0
    _last_new_names: List[str] = []
    _final_new_tracks: List[str] = []

    # Tracking-Status (modal)
    _start_frame = 0
    _end_frame = 0
    _current_frame = 0

    # Reduktions-Tests (Struktur beibehalten)
    _reduction_factors = [0.95, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01]
    _min_threshold = 0.00001

    # ------------------------------------------------------------------------
    #  Start
    # ------------------------------------------------------------------------

    def execute(self, context: Context):
        self._scene = context.scene
        self._clip = get_active_clip(context)
        if self._clip is None:
            self.report({'ERROR'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        # Bereich/Space holen
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        # Clip- und Tracking-Parameter
        self._hz, self._vc = self._clip.size
        tracking_settings = getattr(self._clip.tracking, "settings", None)
        self._ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
        self._pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
        self._sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100
        self._tr = 0.0001

        # Zielwert NUR aus UI-Property (exakt wie in DetectAdapt)
        self._ef_target = int(self._scene.kaiserlich_markers_per_frame)
        self._tolerance = self._ef_target * 0.10  # 10% Toleranz

        # Abgeleiteter Startwert md (exakt wie in DetectAdapt-Fallback)
        self._last_md = self._hz * 0.025

        # Frames
        self._start_frame = self._scene.frame_start
        self._end_frame = self._scene.frame_end
        self._current_frame = max(self._start_frame, int(self._scene.frame_current))

        # Playhead setzen
        self._space.clip_user.frame_current = self._current_frame
        self._scene.frame_current = self._current_frame

        # Baselines
        self._pre_snapshot = snapshot_active_markers(context)
        if self._clip and getattr(self._clip, "tracking", None):
            self._baseline_start_tracknames = {t.name for t in self._clip.tracking.tracks}
        else:
            self._baseline_start_tracknames = set()

        # min_distance per Frame ggf. laden + Interpolation (exakte DetectAdapt-Logik)
        self._last_md = self._load_or_interpolate_md_for_frame(self._scene, self._current_frame, self._last_md)

        # Timer und Modal-Loop
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._phase = "detect"
        self._detect_loop = 0

        print("\n[Kaiserlich Tracker][DeepTest] Starte modalen Deep-Threshold-Test …")
        print(f"[DeepTest][Init] target={self._ef_target}, tol=±{self._tolerance:.1f}, "
              f"hz={self._hz}, vc={self._vc}, margin={self._ma}, pattern={self._pz}, "
              f"start_md={self._last_md:.2f}, start_frame={self._current_frame}, end_frame={self._end_frame}")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    #  Modal-Loop
    # ------------------------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'ESC':
            print("[DeepTest][Modal] ❌ Benutzerabbruch.")
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._phase == "detect":
            done = self._detect_adapt_step(context)
            if done:
                # Selektion finaler neuer Tracks & Wechsel in Tracking
                self._finalize_detection_select_new(context)
                self._phase = "track"
            return {'RUNNING_MODAL'}

        if self._phase == "track":
            done = self._track_step(context)
            if done:
                self._finish(context, cancelled=False)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    #  DetectAdapt — EIN Timer-Schritt pro Iteration (1:1-Logik)
    # ------------------------------------------------------------------------

    def _detect_adapt_step(self, context: Context) -> bool:
        """
        Führt genau eine Iteration der DetectAdapt-Schleife aus.
        Rückgabe True => Detect-Phase fertig (Ziel erreicht oder max_loops).
        """
        self._detect_loop += 1
        loop = self._detect_loop
        max_loops = self._detect_loop_max
        scene = self._scene

        print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop} ---")
        print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {self._last_md:.2f}")

        # Detect
        detect_features(
            context,
            placement='FRAME',
            margin=self._ma,
            threshold=self._tr,
            min_distance=int(max(1, round(self._last_md)))
        )

        # Nach Detect: Selektion zurücksetzen (wie im DetectAdapt)
        clip = getattr(context.space_data, 'clip', None)
        if clip and getattr(clip, 'tracking', None):
            for trk in clip.tracking.tracks:
                try:
                    trk.select = False
                except Exception:
                    pass

        # Snapshot nach Detect
        post_snapshot = snapshot_active_markers(context)
        alte_marker, neue_marker = classify_markers(self._pre_snapshot, post_snapshot)

        print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker erkannt: {len(alte_marker)}")
        print(f"[Kaiserlich Tracker][DetectAdapt] Neue Marker erkannt: {len(neue_marker)}")
        if len(neue_marker) > 0:
            print("   ➤ Beispiel neue Marker:", [m['track'] for m in neue_marker[:5]])
        if len(alte_marker) > 0:
            print("   ➤ Beispiel alte Marker:", [m['track'] for m in alte_marker[:5]])

        am = len(neue_marker)

        # Cleanup
        cleaned_new, deleted_old = cleanup_new_markers(
            context,
            alte_marker,
            neue_marker,
            pz=self._pz,
            hz=self._hz,
            vc=self._vc
        )
        self._deleted_old_count += int(deleted_old)

        # Logging wie DetectAdapt
        deleted_old_names = [m['track'] for m in alte_marker
                             if m['track'] not in [n['track'] for n in post_snapshot]]
        if deleted_old_names:
            print(f"[⚠️ Kaiserlich Tracker][DetectAdapt] WARNUNG: Alte Marker gelöscht: {deleted_old_names}")

        remaining = len(cleaned_new)
        print(f"[Kaiserlich Tracker][DetectAdapt] Nach Cleanup: {remaining} neue Marker übrig, {deleted_old} alte gelöscht")

        # Zielprüfung
        diff = remaining - self._ef_target
        tolerance = self._tolerance
        if abs(diff) <= tolerance:
            print(f"[Kaiserlich Tracker][DetectAdapt] Ziel erreicht: {remaining}/{self._ef_target} Marker "
                  f"(Toleranz ±{tolerance:.1f})")
            # Finale Namen für spätere Selektion/Tracking merken
            self._last_new_names = [m['track'] for m in cleaned_new]
            # min_distance pro Frame speichern + Interpolation (exakt)
            self._store_md_with_interpolation(scene, self._current_frame, self._last_md)
            return True

        # Dynamische Anpassung des Mindestabstands (exakt wie DetectAdapt)
        if am > 0:
            ratio = self._ef_target / am
            factor = max(0.5, min(2.0, ratio))
            new_md = self._last_md / factor
            self._last_md = max(1.0, new_md)
        else:
            self._last_md = self._last_md * 1.5
            print("[Kaiserlich Tracker][DetectAdapt] Keine neuen Marker, erhöhe min_distance stark")

        # Marker dieser Iteration löschen, wenn weitere Schleifen folgen
        if loop < max_loops:
            self._last_new_names = [m['track'] for m in neue_marker]
            delete_tracks_by_names(context, self._last_new_names)
            print(f"[Kaiserlich Tracker][DetectAdapt] {len(self._last_new_names)} neue Marker gelöscht für nächsten Zyklus")
            time.sleep(0.05)
            return False

        # Max Loops erreicht → aktuellen Stand übernehmen
        self._last_new_names = [m['track'] for m in cleaned_new]
        self._store_md_with_interpolation(scene, self._current_frame, self._last_md)
        print("[Kaiserlich Tracker][DetectAdapt] ⚠️ Max. Loops erreicht – übernehme aktuellen Zustand.")
        return True

    def _finalize_detection_select_new(self, context: Context):
        """Selektiert NUR neue Tracks (nicht in globaler Baseline), identisch zur DetectAdapt-Idee."""
        clip = getattr(context.space_data, 'clip', None)
        if not (clip and getattr(clip, 'tracking', None)):
            return
        tracking = clip.tracking

        # Neue Tracks = alle, die nicht in der Baseline existierten
        new_tracks = [trk for trk in tracking.tracks if trk.name not in self._baseline_start_tracknames]
        try:
            for trk in tracking.tracks:
                trk.select = False
            for new_trk in new_tracks:
                new_trk.select = True
            self._final_new_tracks = [t.name for t in new_tracks]
            print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")
        except Exception:
            pass

    # ------------------------------------------------------------------------
    #  Track-Phase — frameweise, modal
    # ------------------------------------------------------------------------

    def _track_step(self, context: Context) -> bool:
        """Trackt selektierte Marker Frame für Frame; beendet am Szenenende."""
        if not self._final_new_tracks:
            print("[DeepTest][Track] ❌ Keine Tracks für Tracking vorhanden.")
            # Trotzdem Metrik erfassen
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            return True

        # Frame setzen
        self._scene.frame_current = self._current_frame
        self._space.clip_user.frame_current = self._current_frame

        # Tracking-Schritt
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )

        if not success:
            print("[DeepTest][Track] ⚠️ Tracking-Fehler. Beende.")
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            delete_tracks_by_names(context, self._final_new_tracks)
            return True

        # Nächster Frame
        self._current_frame += 1
        if self._current_frame > self._end_frame:
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            print(f"[DeepTest][Track] ✅ Beendet. Total Track Length = {total_len}")
            # nur die neu erzeugten Tracks löschen
            delete_tracks_by_names(context, self._final_new_tracks)
            return True

        return False

    # ------------------------------------------------------------------------
    #  min_distance pro Frame laden/ableiten (1:1 wie DetectAdapt)
    # ------------------------------------------------------------------------

    def _load_or_interpolate_md_for_frame(self, scene: bpy.types.Scene, frame_num: int, fallback_md: float) -> float:
        """Repliziert das Lade-/Interpolationsverhalten von DetectAdapt."""
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                return float(md_dict[str(frame_num)])
            else:
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
        """Speichert md und interpoliert wie in DetectAdapt."""
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
                    interp_val = v_start + (v_end - v_start) * t
                    md_dict[str(f)] = float(interp_val)

    # ------------------------------------------------------------------------
    #  Threshold-Test-Funktionen (Struktur beibehalten; Metrik aus Scene)
    # ------------------------------------------------------------------------

    def _test_rot_pair(self, context: Context, target_value: int, clip) -> Tuple[float, float]:
        scene = context.scene
        hz, vc = clip.size[0], clip.size[1]
        ratio = (hz / vc) if vc > 0 else 1.0
        best_x = best_y = 1.0
        min_value = self._min_threshold
        current_target = max(target_value, 0)

        for factor in self._reduction_factors:
            current_value = 1.0
            while current_value > min_value:
                current_value *= factor
                set_scene_props(scene,
                                kaiserlich_rot_thresh_x=current_value,
                                kaiserlich_rot_thresh_y=current_value * ratio)
                length = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
                if length >= current_target:
                    best_x = current_value
                    best_y = current_value * ratio
                    current_target = length
                    break
        return best_x, best_y

    def _test_single_threshold(self, context: Context, prop_name: str, target_value: int,
                               freeze_others: Optional[Dict[str, float]] = None) -> float:
        scene = context.scene
        best_value = 1.0
        min_value = self._min_threshold
        current_target = max(target_value, 0)

        for factor in self._reduction_factors:
            current_value = 1.0
            while current_value > min_value:
                current_value *= factor
                if freeze_others:
                    set_scene_props(scene, **freeze_others)
                set_scene_props(scene, **{prop_name: current_value})
                length = int(scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0))
                if length >= current_target:
                    best_value = current_value
                    current_target = length
                    break
        return best_value

    def _test_rot_scale_pair(self, context: Context, target_value: int) -> Tuple[float, float]:
        rot = self._test_single_threshold(context, 'kaiserlich_rot_scale_thresh_rot', target_value,
                                          freeze_others={'kaiserlich_rot_scale_thresh_scale': 0.0})
        scale = self._test_single_threshold(context, 'kaiserlich_rot_scale_thresh_scale', target_value,
                                            freeze_others={'kaiserlich_rot_scale_thresh_rot': 0.0})
        return rot, scale

    # ------------------------------------------------------------------------
    #  Abschluss
    # ------------------------------------------------------------------------

    def _finish(self, context: Context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        msg = "❌ Deep Test abgebrochen." if cancelled else "✅ Deep Test abgeschlossen."
        print(f"[DeepTest][Modal] {msg}")
        self.report({'INFO'}, "Deep Test abgebrochen." if cancelled else "Deep Test abgeschlossen.")


# ============================================================================
#  Registrierung
# ============================================================================

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)

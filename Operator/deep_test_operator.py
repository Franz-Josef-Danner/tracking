# deep_test_operator.py
import bpy
import time
from typing import Any, Dict, Optional, Tuple
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
#  MODALER DEEP-TEST-OPERATOR
# ============================================================================

class KAISERLICHTRACKER_OT_deep_test_operator(Operator):
    """Führt einen vollständigen Deep-Threshold-Test mit adaptiver Marker-Erkennung
    und modalem Tracking durch."""
    bl_idname = "kaiserlich_tracker.deep_test_operator"
    bl_label = "Kaiserlich Tracker — Deep Test (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # ------------------------------------------------------------------------
    #  Parameter / interne Variablen
    # ------------------------------------------------------------------------
    _reduction_factors = [0.95, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01]
    _min_threshold = 0.00001
    _timer = None
    _phase = "detect"
    _context_cache = None
    _window = None
    _area = None
    _region = None
    _space = None
    _clip = None
    _scene = None
    _start_frame = 0
    _end_frame = 0
    _current_frame = 0
    _final_tracks = []
    _loop_counter = 0
    _max_loops = 6
    _ma = 100
    _pz = 50
    _hz = 0
    _vc = 0
    _min_distance = 0
    _target_markers = 0
    _tolerance = 0
    _pre_snapshot = []
    _results: Dict[str, float] = {}

    # ------------------------------------------------------------------------
    #  Start
    # ------------------------------------------------------------------------

    def execute(self, context: Context):
        self._scene = context.scene
        self._clip = get_active_clip(context)
        if self._clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        print("\n[Kaiserlich Tracker][DeepTest] Starte modalen Deep-Threshold-Test …")

        # Setup
        self._window, self._area, self._region, self._space = find_clip_editor_area(self._clip)
        if not self._window:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        self._hz, self._vc = self._clip.size
        tracking = self._clip.tracking
        self._ma = getattr(tracking.settings, "margin", 100)
        self._pz = getattr(tracking.settings, "pattern_size", 50)
        self._min_distance = max(1, int(self._hz * 0.05))

        self._target_markers = int(self._scene.get("kaiserlich_markers_per_frame", 150))
        self._tolerance = self._target_markers * 0.1
        self._start_frame = self._scene.frame_start
        self._end_frame = self._scene.frame_end
        self._current_frame = self._start_frame

        self._space.clip_user.frame_current = self._start_frame
        self._scene.frame_current = self._start_frame

        # Snapshot für Vergleich
        self._pre_snapshot = snapshot_active_markers(context)

        # Timer initialisieren
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._phase = "detect"
        self._loop_counter = 0
        print("[DeepTest][Modal] Initialisierung abgeschlossen. Beginne mit adaptiver Marker-Erkennung …")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    #  Modal Loop
    # ------------------------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'ESC':
            print("[DeepTest][Modal] ❌ Benutzerabbruch.")
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._phase == "detect":
            self._run_detect_phase(context)
            return {'RUNNING_MODAL'}

        elif self._phase == "track":
            done = self._run_track_phase(context)
            if done:
                self._finish(context)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}

        elif self._phase == "evaluate":
            self._finish(context)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    #  Detect-Phase (adaptiert von DetectAdapt)
    # ------------------------------------------------------------------------

    def _run_detect_phase(self, context: Context):
        self._loop_counter += 1
        if self._loop_counter > self._max_loops:
            print("[DeepTest][Detect] ❌ Max. Versuche erreicht, keine passenden Marker gefunden.")
            self._phase = "track"
            return

        print(f"[DeepTest][Detect] --- LOOP {self._loop_counter} ---  (min_distance={self._min_distance})")

        detect_features(context, placement='FRAME',
                        margin=self._ma, threshold=0.01, min_distance=self._min_distance)

        post_snapshot = snapshot_active_markers(context)
        old, new = classify_markers(self._pre_snapshot, post_snapshot)

        cleaned_new, _ = cleanup_new_markers(context, old, new, pz=self._pz, hz=self._hz, vc=self._vc)
        print(f"[DeepTest][Detect] Nach Cleanup: {len(cleaned_new)} Marker (Ziel={self._target_markers})")

        if abs(len(cleaned_new) - self._target_markers) <= self._tolerance:
            self._final_tracks = [m['track'] for m in cleaned_new]
            for tr in self._clip.tracking.tracks:
                tr.select = tr.name in self._final_tracks
            print(f"[DeepTest][Detect] ✅ Ziel erreicht mit {len(self._final_tracks)} Tracks.")
            self._phase = "track"
            return

        # Dynamische Anpassung von min_distance
        if len(cleaned_new) > self._target_markers:
            self._min_distance = int(self._min_distance * 1.2)
        else:
            self._min_distance = max(1, int(self._min_distance * 0.8))

        delete_tracks_by_names(context, [m['track'] for m in new])
        time.sleep(0.05)

    # ------------------------------------------------------------------------
    #  Track-Phase (frameweise)
    # ------------------------------------------------------------------------

    def _run_track_phase(self, context: Context) -> bool:
        if not self._final_tracks:
            print("[DeepTest][Track] ❌ Keine Tracks für Tracking vorhanden.")
            return True

        self._scene.frame_current = self._current_frame
        self._space.clip_user.frame_current = self._current_frame

        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=False, sequence=False
        )

        if not success:
            print("[DeepTest][Track] ⚠️ Tracking-Fehler.")
            return True

        # Fortschritt
        self._current_frame += 1
        if self._current_frame > self._end_frame:
            total_len = int(get_total_track_length(context, start_frame=self._start_frame))
            self._scene[SCENE_TOTAL_TRACK_LEN_BASE] = total_len
            print(f"[DeepTest][Track] ✅ Beendet. Total Track Length = {total_len}")
            delete_tracks_by_names(context, self._final_tracks)
            return True

        return False

    # ------------------------------------------------------------------------
    #  Abschluss
    # ------------------------------------------------------------------------

    def _finish(self, context: Context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        if cancelled:
            print("[DeepTest][Modal] ❌ Abgebrochen.")
        else:
            print("[DeepTest][Modal] ✅ Deep Test abgeschlossen.")

        self.report({'INFO'}, "Deep Test abgeschlossen.")

    # ------------------------------------------------------------------------
    #  Bestehende Threshold-Test-Funktionen (unverändert)
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
                set_scene_props(scene, kaiserlich_rot_thresh_x=current_value, kaiserlich_rot_thresh_y=current_value * ratio)
                length = self._scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0)
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
                length = self._scene.get(SCENE_TOTAL_TRACK_LEN_BASE, 0)
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


# ============================================================================
#  Registrierung
# ============================================================================

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_deep_test_operator)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_deep_test_operator)

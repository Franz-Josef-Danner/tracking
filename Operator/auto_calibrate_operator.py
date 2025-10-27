# Operator/auto_calibrate_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set, Deque
from collections import deque
from dataclasses import dataclass, field

# ---- Helper-Imports ---------------------------------------------------------
from ..Helper.util_clip import (
    get_active_clip,
    list_track_names_from_clip,
    get_current_track_names,
)
from ..Helper.scene import (
    get_scene_range,
    get_start_frame as sc_get_start_frame,
    get_end_frame as sc_get_end_frame,
)
from ..Helper.reset_helper import (
    reset_all_thresholds,
    get_scene_value,
    set_scene_value,
    THRESH_LIST,
)
from ..Helper.playhead_helper import (
    get_start_frame as ph_get_start_frame,
    reset_to_frame,
)
from ..Helper.newmarker import (
    diff_markers,
    classify_markers,
)
from ..Helper.find_clip_editor_area import (
    find_clip_editor_area,
)
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names


# ----------------------------------------------------------------------------
#  Modal-Operator (nicht-blockierend)
# ----------------------------------------------------------------------------

@dataclass
class _AutoCalibState:
    initialized: bool = False
    done: bool = False
    step: int = 0
    notes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    did_reset_thresholds: bool = False
    did_detect_adapt: bool = False


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kaiserlich Tracker — Auto Calibrate (modal)"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    # interne Runtime
    _timer: Optional[Any] = None
    _state: _AutoCalibState

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # Timer für nicht-blockierenden Modal-Loop
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)  # ~20 Hz
        wm.modal_handler_add(self)

        # State init
        self._state = _AutoCalibState()

        # Grundprüfung Clip
        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        self._state.notes.append("Init OK (modal).")
        return {'RUNNING_MODAL'}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)

        if event.type == 'TIMER':
            if not self._state.initialized:
                # Einmalige leichte Initialisierung hier
                self._state.initialized = True
                self._state.notes.append("Initialized.")
                return {'RUNNING_MODAL'}

            # 1) Erste Ausführung: Thresholds neutralisieren (→ 1.0)
            if not self._state.did_reset_thresholds:
                try:
                    reset_all_thresholds(context, active_props=[])  # wirklich alle Gruppen
                    self._state.did_reset_thresholds = True
                    self._state.notes.append("Thresholds reset to 1.0 (all groups).")
                except Exception as ex:
                    self._state.notes.append(f"Threshold reset failed: {ex!r}")
                return {'RUNNING_MODAL'}

            # 2) Detect-Adapt inline (einmalig) – keine externen Operator-Aufrufe
            if not self._state.did_detect_adapt:
                try:
                    self._detect_adapt_inline(context)
                    self._state.did_detect_adapt = True
                    self._state.notes.append("Detect-Adapt executed (inline).")
                except Exception as ex:
                    self._state.notes.append(f"Detect-Adapt failed: {ex!r}")
                return {'RUNNING_MODAL'}

            # 3) (Platzhalter) Weitere Kalibrier-Schritte
            self._state.done = True
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _teardown(self, context: bpy.types.Context, cancelled: bool):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None

        if cancelled:
            self.report({'INFO'}, "Auto Calibrate abgebrochen.")
            return {'CANCELLED'}
        else:
            self.report({'INFO'}, "Auto Calibrate abgeschlossen.")
            return {'FINISHED'}

    # ------------------------------------------------------------------------
    # INLINE-IMPLEMENTIERUNG von Detect-Adapt (aus detect_adapt_operator.py)
    # ------------------------------------------------------------------------
    def _detect_adapt_inline(self, context: bpy.types.Context) -> None:
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

        # Bootstrap-Parameter laden oder lokal berechnen
        params = scene.get("bootstrap_params", None)

        if params:
            md = float(params.get('md', 100))
            ma = int(params.get('ma', 30))
            tr = float(params.get('tr', 0.5))
            pz = int(params.get('pz', 50))
            sz = int(params.get('sz', 0))
            hz = params.get('hz', 1)
            vc = params.get('vc', False)
        else:
            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                raise RuntimeError("Kein aktiver Clip verfügbar (Fallback fehlgeschlagen).")

            hz = clip.size[0]
            vc = clip.size[1]

            scene_obj = getattr(context, "scene", None)
            frame_end = scene_obj.frame_end if scene_obj else None

            tracking_settings = getattr(clip.tracking, "settings", None)
            ma = getattr(tracking_settings, "margin", 100) if tracking_settings else 100
            pz = getattr(tracking_settings, "pattern_size", 50) if tracking_settings else 50
            sz = getattr(tracking_settings, "search_size", 100) if tracking_settings else 100

            md = hz * 0.025
            tr = 0.0001
            za = ef_target * 4
            og = math.ceil(za * 1.1)
            ug = math.floor(za * 0.9)

            print(f"[Kaiserlich Tracker][DetectAdapt][Fallback] "
                  f"hz={hz}, vc={vc}, margin={ma}, md={md:.2f}, "
                  f"pattern={pz}, search={sz}, tr={tr}, og={og}, ug={ug}, frame_end={frame_end}")

        # BASELINE-FIX
        pre_snapshot = snapshot_active_markers(context)

        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        baseline_start_tracknames: Set[str] = set()
        if tracking:
            baseline_start_tracknames = {t.name for t in tracking.tracks}

        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | BaselineTracks: {len(baseline_start_tracknames)}")

        max_loops = 8
        loop = 0
        final_new_marker_count = 0
        frame_num = scene.frame_current

        # Versuch gespeicherten Wert zu laden
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])
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
                        last_md = v1 + (v2 - v1) * t
                    else:
                        last_md = md
                else:
                    last_md = md
        else:
            last_md = md

        deleted_old = 0

        while loop < max_loops:
            loop += 1
            print(f"\n[Kaiserlich Tracker][DetectAdapt] --- LOOP {loop} ---")
            print(f"[Kaiserlich Tracker][DetectAdapt] Aktuelles min_distance = {last_md:.2f}")

            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(last_md)))
            )

            clip = getattr(context.space_data, 'clip', None)
            if clip and getattr(clip, 'tracking', None):
                for trk in clip.tracking.tracks:
                    try:
                        trk.select = False
                    except Exception:
                        pass

            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

            print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker erkannt: {len(alte_marker)}")
            print(f"[Kaiserlich Tracker][DetectAdapt] Neue Marker erkannt: {len(neue_marker)}")

            am = len(neue_marker)
            final_new_marker_count = am

            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            print(f"[Kaiserlich Tracker][DetectAdapt] Nach Cleanup: {len(cleaned_new)} neue Marker übrig, {deleted_old} alte gelöscht")

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10
            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][DetectAdapt] Ziel erreicht: {remaining}/{ef_target} Marker (Toleranz ±{tolerance:.1f})")
                break

            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                new_md = last_md / factor
                last_md = max(1.0, new_md)
            else:
                last_md *= 1.5
                print("[Kaiserlich Tracker][DetectAdapt] Keine neuen Marker, erhöhe min_distance stark")

            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                print(f"[Kaiserlich Tracker][DetectAdapt] {len(neue_marker)} neue Marker gelöscht für nächsten Zyklus")
                time.sleep(0.1)

        clip = getattr(context.space_data, 'clip', None)
        if clip and getattr(clip, 'tracking', None):
            tracking = clip.tracking
            new_tracks = [trk for trk in tracking.tracks if trk.name not in baseline_start_tracknames]
            try:
                for trk in tracking.tracks:
                    trk.select = False
                for new_trk in new_tracks:
                    new_trk.select = True
                print(f"[Kaiserlich Tracker][DetectAdapt] Final selektierte Marker: {len(new_tracks)}")
            except Exception:
                pass

        frame_num = scene.frame_current
        md_value = float(last_md)
        if "min_distance_values" not in scene:
            scene["min_distance_values"] = {}
        md_dict = scene["min_distance_values"]
        known_list = list(md_dict.get("known_frames", []))
        if frame_num not in known_list:
            known_list.append(frame_num)
            known_list.sort()
        md_dict["known_frames"] = known_list
        md_dict[str(frame_num)] = md_value

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
                    md_dict[str(f)] = interp_val

        print(f"[Kaiserlich Tracker][DetectAdapt] Frame {frame_num}: final min_distance = {md_value:.2f}")
        return None


# ----------------------------------------------------------------------------
#  Registration
# ----------------------------------------------------------------------------

_classes = (KAISERLICHTRACKER_OT_auto_calibrate,)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

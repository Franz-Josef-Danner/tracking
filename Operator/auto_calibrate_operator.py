# Operator/auto_calibrate_operator.py
import bpy
import time
import math
from typing import Optional, List, Dict, Any, Tuple, Set, Deque
from collections import deque
from dataclasses import dataclass, field

# ---- Helper-Importe ---------------------------------------------------------
from ..Helper.util_clip import get_active_clip
from ..Helper.scene import get_end_frame
from ..Helper.reset_helper import reset_all_thresholds
from ..Helper.playhead_helper import reset_to_frame
from ..Helper.newmarker import classify_markers
from ..Helper.find_clip_editor_area import find_clip_editor_area
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.filter_active_tracks import filter_active_tracks_at_frame
from ..Helper.track_markers_helper import track_markers_with_override
from ..Helper.selection_helper import collect_selected_track_names
from ..Helper.formula_helper import apply_formula_on_selected_tracks


# ----------------------------------------------------------------------------
#  Modal-Operator mit deterministischer State-Steuerung
# ----------------------------------------------------------------------------

@dataclass
class _AutoCalibState:
    initialized: bool = False
    done: bool = False
    step: int = 0
    notes: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    did_reset_thresholds: bool = False
    did_detect_adapt: bool = False
    did_track_cycle: bool = False
    detect_adapt_done_confirmed: bool = False


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kaiserlich Tracker — Auto Calibrate (komplette Pipeline)"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    _timer: Optional[Any] = None
    _state: _AutoCalibState

    # ------------------------------------------------------------------------
    # Invoke / Modal Setup
    # ------------------------------------------------------------------------
    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._state = _AutoCalibState()

        clip = get_active_clip(context)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver MovieClip gefunden.")
            return {'CANCELLED'}

        self._state.notes.append("Init OK (modal).")
        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Haupt-State-Machine
    # ------------------------------------------------------------------------
    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # 0) Initialisierung
        if not self._state.initialized:
            self._state.initialized = True
            print("[Kaiserlich Tracker][AutoCalibrate] Initialized.")
            return {'RUNNING_MODAL'}

        # 1) Threshold-Reset
        if not self._state.did_reset_thresholds:
            reset_all_thresholds(context, active_props=[])
            self._state.did_reset_thresholds = True
            print("[Kaiserlich Tracker][AutoCalibrate] Thresholds reset → 1.0")
            return {'RUNNING_MODAL'}

        # 2) Detect-Adapt
        if not self._state.did_detect_adapt:
            print("[Kaiserlich Tracker][AutoCalibrate] Detect-Adapt gestartet.")
            self._detect_adapt_inline(context)
            self._state.did_detect_adapt = True
            return {'RUNNING_MODAL'}

        # 3) Prüfen, ob Detect-Adapt abgeschlossen
        if self._state.did_detect_adapt and not self._state.detect_adapt_done_confirmed:
            # Noch keine Bestätigung aus Detect-Adapt erhalten → warten
            return {'RUNNING_MODAL'}

        # 4) Track-Cycle erst nach bestätigtem Detect-Adapt
        if not self._state.did_track_cycle and self._state.detect_adapt_done_confirmed:
            self._track_cycle_inline(context)
            self._state.did_track_cycle = True
            print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle gestartet.")
            return {'RUNNING_MODAL'}

        # 5) Abschluss
        if not self._state.done and self._state.did_track_cycle:
            self._state.done = True
            return self._teardown(context, cancelled=False)

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Detect-Adapt Inline (komplett, mit Flag-Setzung)
    # ------------------------------------------------------------------------
    def _detect_adapt_inline(self, context: bpy.types.Context):
        scene = context.scene
        ef_target = int(scene.kaiserlich_markers_per_frame)

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

        # Baseline erfassen
        pre_snapshot = snapshot_active_markers(context)
        clip = getattr(context.space_data, "clip", None)
        tracking = getattr(clip, "tracking", None) if clip else None
        baseline_start_tracknames: Set[str] = {t.name for t in tracking.tracks} if tracking else set()

        print(f"[Kaiserlich Tracker][DetectAdapt] Ausgangsmarker: {len(pre_snapshot)} | BaselineTracks: {len(baseline_start_tracknames)}")

        max_loops = 8
        loop = 0
        final_new_marker_count = 0
        frame_num = scene.frame_current
        deleted_old = 0

        last_md = md
        if "min_distance_values" in scene:
            md_dict = scene["min_distance_values"]
            if str(frame_num) in md_dict:
                last_md = float(md_dict[str(frame_num)])

        # Adaptive Schleife
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

            # Nach Detect: neue Marker erfassen
            post_snapshot = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(pre_snapshot, post_snapshot)

            print(f"[Kaiserlich Tracker][DetectAdapt] Alte Marker: {len(alte_marker)}, Neue Marker: {len(neue_marker)}")
            am = len(neue_marker)
            final_new_marker_count = am

            # Cleanup
            cleaned_new, deleted_old = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker,
                pz=pz,
                hz=hz,
                vc=vc
            )

            remaining = len(cleaned_new)
            diff = remaining - ef_target
            tolerance = ef_target * 0.10

            if abs(diff) <= tolerance:
                print(f"[Kaiserlich Tracker][DetectAdapt] Ziel erreicht: {remaining}/{ef_target}")
                self._state.detect_adapt_done_confirmed = True
                break

            # Dynamische Anpassung
            if am > 0:
                ratio = ef_target / am
                factor = max(0.5, min(2.0, ratio))
                last_md = max(1.0, last_md / factor)
            else:
                last_md *= 1.5
                print("[DetectAdapt] Keine neuen Marker → erhöhe min_distance stark")

            if loop < max_loops:
                delete_tracks_by_names(context, [m['track'] for m in neue_marker])
                time.sleep(0.1)

        # Falls Schleife endet ohne Ziel
        if not self._state.detect_adapt_done_confirmed:
            print("[⚠️ DetectAdapt] Keine stabile Markeranzahl erreicht – fahre dennoch fort.")
            self._state.detect_adapt_done_confirmed = True

        # Selektion sicherstellen
        if clip and getattr(clip, 'tracking', None):
            for trk in clip.tracking.tracks:
                trk.select = True
            print("[DetectAdapt] Alle Marker nach Abschluss selektiert.")

    # ------------------------------------------------------------------------
    # Track-Cycle Inline (aus track_operator.py)
    # ------------------------------------------------------------------------
    def _track_cycle_inline(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            raise RuntimeError("Kein aktiver Clip verfügbar.")

        start_frame = scene.frame_start
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        original_selected = collect_selected_track_names(context)
        if not original_selected:
            tracking = getattr(clip, "tracking", None)
            if tracking:
                original_selected = [t.name for t in tracking.tracks]
                for tr in tracking.tracks:
                    tr.select = True
                print(f"[TrackCycle] ⚠️ Keine Selektion – alle {len(original_selected)} Tracks aktiviert.")
            else:
                raise RuntimeError("Keine Tracks verfügbar für Tracking.")

        processing_names = list(original_selected)
        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

        current_frame = max(start_frame, int(scene.frame_current))
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        tracking = clip.tracking
        frames_processed = 0
        max_frames = 0
        print(f"[Kaiserlich Tracker][TrackCycle] Start {start_frame} → {end_frame}")

        while current_frame <= end_frame:
            # Formel anwenden
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[TrackCycle] Formel-Fehler: {e}")

            success = track_markers_with_override(
                window, area, region, space,
                backwards=False, sequence=False
            )
            if not success:
                print("[TrackCycle] Tracking-Fehler – Abbruch.")
                break

            if space.clip_user.frame_current == current_frame:
                space.clip_user.frame_current += 1
            if space.clip_user.frame_current > end_frame:
                space.clip_user.frame_current = end_frame

            scene.frame_current = space.clip_user.frame_current
            current_frame = space.clip_user.frame_current
            frames_processed += 1

            processing_names, _ = filter_active_tracks_at_frame(
                context, processing_names, current_frame
            )

            if current_frame >= end_frame:
                print("[TrackCycle] ✅ Szenenende erreicht.")
                break
            if not processing_names:
                print("[TrackCycle] ✅ Keine aktiven Tracks mehr.")
                break
            if max_frames > 0 and frames_processed >= max_frames:
                print("[TrackCycle] ⚠️ Sicherheitslimit erreicht.")
                break

        # Cleanup
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[TrackCycle] Frame-Reset Fehler: {e}")

        print("[Kaiserlich Tracker][TrackCycle] ✅ Zyklus beendet.")
        return None

    # ------------------------------------------------------------------------
    # Cleanup / Teardown
    # ------------------------------------------------------------------------
    def _teardown(self, context: bpy.types.Context, cancelled: bool):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
        msg = "Auto Calibrate abgebrochen." if cancelled else "Auto Calibrate abgeschlossen."
        self.report({'INFO'}, msg)
        return {'CANCELLED' if cancelled else 'FINISHED'}


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

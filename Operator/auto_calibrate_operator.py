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
#  Modal-Operator
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


class KAISERLICHTRACKER_OT_auto_calibrate(bpy.types.Operator):
    """Kaiserlich Tracker — Auto Calibrate (komplette Pipeline)"""
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label = "Kaiserlich Tracker — Auto Calibrate"
    bl_options = {'REGISTER', 'UNDO'}

    _timer: Optional[Any] = None
    _state: _AutoCalibState

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

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == 'ESC':
            return self._teardown(context, cancelled=True)

        if event.type == 'TIMER':
            if not self._state.initialized:
                self._state.initialized = True
                self._state.notes.append("Initialized.")
                return {'RUNNING_MODAL'}

            # 1) Thresholds resetten
            if not self._state.did_reset_thresholds:
                reset_all_thresholds(context, active_props=[])
                self._state.did_reset_thresholds = True
                print("[Kaiserlich Tracker][AutoCalibrate] Thresholds reset → 1.0")
                return {'RUNNING_MODAL'}

            # 2) Detect-Adapt Inline
            if not self._state.did_detect_adapt:
                self._detect_adapt_inline(context)
                self._state.did_detect_adapt = True
                print("[Kaiserlich Tracker][AutoCalibrate] Detect-Adapt done.")
                return {'RUNNING_MODAL'}

            # 3) Track-Cycle Inline
            if not self._state.did_track_cycle:
                self._track_cycle_inline(context)
                self._state.did_track_cycle = True
                print("[Kaiserlich Tracker][AutoCalibrate] Track-Cycle done.")
                return {'RUNNING_MODAL'}

            self._state.done = True
            return self._teardown(context, cancelled=False)

        return {'RUNNING_MODAL'}

    # ------------------------------------------------------------------------
    # Detect-Adapt (wie bisher)
    # ------------------------------------------------------------------------
    def _detect_adapt_inline(self, context: bpy.types.Context):
        # ... (bereits vorhandene Detect-Adapt-Logik hier unverändert)
        print("[Detect-Adapt Inline] Start (Placeholder).")
        # → dein bestehender Detect-Adapt-Code bleibt hier

    # ------------------------------------------------------------------------
    # Track-Cycle Inline (aus track_operator.py übernommen)
    # ------------------------------------------------------------------------
    def _track_cycle_inline(self, context: bpy.types.Context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            raise RuntimeError("Kein aktiver Clip verfügbar.")

        # Start / Endframes
        start_frame = scene.frame_start
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        # Selektion
        original_selected = collect_selected_track_names(context)
        if not original_selected:
            raise RuntimeError("Keine Tracks selektiert.")

        processing_names = list(original_selected)

        # CLIP_EDITOR-Area finden
        window, area, region, space = find_clip_editor_area(clip)
        if not window:
            raise RuntimeError("Keine CLIP_EDITOR Area gefunden.")

        # Frame-Setup
        current_frame = max(start_frame, int(scene.frame_current))
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        histories: Dict[str, Deque[Tuple[int, float, float]]] = {
            name: deque(maxlen=10) for name in processing_names
        }

        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        print(f"[Kaiserlich Tracker][TrackCycle] Start: {start_frame} → {end_frame}")

        frames_processed = 0
        max_frames = 0  # optionales Sicherheitslimit

        while current_frame <= end_frame:
            # Historien aktualisieren
            for name in list(processing_names):
                tr = tracking.tracks.get(name)
                if not tr:
                    continue
                mk = tr.markers.find_frame(current_frame)
                if mk:
                    histories[name].append((current_frame, mk.co[0], mk.co[1]))

            # Formel anwenden
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception as e:
                print(f"[Kaiserlich Tracker][TrackCycle] Formel-Fehler: {e}")

            # Tracking-Schritt
            success = track_markers_with_override(
                window, area, region, space,
                backwards=False, sequence=False
            )
            if not success:
                print("[Kaiserlich Tracker][TrackCycle] Tracking-Fehler.")
                break

            # Frame-Update
            if space.clip_user.frame_current == current_frame:
                space.clip_user.frame_current += 1
            if space.clip_user.frame_current > end_frame:
                space.clip_user.frame_current = end_frame

            scene.frame_current = space.clip_user.frame_current
            current_frame = space.clip_user.frame_current
            frames_processed += 1

            # Aktive Tracks prüfen
            processing_names, _ = filter_active_tracks_at_frame(
                context, processing_names, current_frame
            )

            # Beendigungsbedingungen
            if current_frame >= end_frame:
                print("[Kaiserlich Tracker][TrackCycle] ✅ Szenenende erreicht.")
                break
            if not processing_names:
                print("[Kaiserlich Tracker][TrackCycle] ✅ Keine aktiven Tracks mehr.")
                break
            if max_frames > 0 and frames_processed >= max_frames:
                print("[Kaiserlich Tracker][TrackCycle] ⚠️ Sicherheitslimit erreicht.")
                break

        # Selektion wiederherstellen
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        try:
            reset_to_frame(context, start_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][TrackCycle] Fehler beim Frame-Reset: {e}")

        print("[Kaiserlich Tracker][TrackCycle] ✅ Zyklus beendet.")
        return None

    # ------------------------------------------------------------------------
    # Teardown
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

# Operator/Master/master_track_operator_backwards.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

# ------------------------------------------------------------
# Helper Imports
# ------------------------------------------------------------
from ...Helper.playhead_helper import reset_to_frame
from ...Helper.scene import get_end_frame, get_start_frame as scene_get_start_frame
from ...Helper.find_clip_editor_area import find_clip_editor_area
from ...Helper.selection_helper import collect_selected_track_names
from ...Helper.filter_active_tracks import filter_active_tracks_at_frame
from ...Helper.track_markers_helper import track_markers_with_override
from ...Helper.frame_track_progress import compute_marker_progress
from ...Helper.adapt_search_size_backward import adapt_search_size_for_calibrate_tracks_backward
from ...Helper.motion_average_backwards import get_from_selected_tracks_backwards
from ...Helper.formula_helper_backward import apply_formula_on_selected_tracks_backwards
from ...Helper.threshold_stats import update_threshold_extrema
from ...Helper.correct.correct_selected_by_ref_motion_backward import correct_motion_by_reference_backward
from ...Helper.correct.correct_selected_by_ref_dynamic_backward import correct_motion_by_dynamic_reference_backward


def store_calibrate_tracks_in_scene(context, track_names: List[str]) -> None:
    scene = context.scene
    if not track_names:
        print("[BACKWARD][CALIBRATE_STORE] ⚠ keine Track-Namen übergeben – Abbruch.")
        return

    try:
        # Alte Einträge bereinigen
        for key in ("calibrate_tracks", "calibrate_tracks_uuid_map"):
            if key in scene:
                del scene[key]
        print("[BACKWARD][CALIBRATE_STORE] Alte Scene-Keys 'calibrate_tracks' & 'calibrate_tracks_uuid_map' bereinigt.")

        clip = getattr(context.space_data, "clip", None)
        if not clip or not getattr(clip, "tracking", None):
            print("[BACKWARD][CALIBRATE_STORE] ⚠ Kein gültiger Clip/Tracking gefunden – nichts gespeichert.")
            return

        # UUID-Map erzeugen
        import uuid as _uuid
        uuid_map: Dict[str, str] = {}
        for name in track_names:
            uuid_map[str(_uuid.uuid4())] = name

        # WICHTIG: jetzt als LISTE speichern, nicht als String
        scene["calibrate_tracks"] = list(track_names)
        scene["calibrate_tracks_uuid_map"] = str(uuid_map)

        print(
            f"[BACKWARD][CALIBRATE_STORE] ✅ {len(track_names)} Tracks in Scene gespeichert "
            f"(calibrate_tracks, calibrate_tracks_uuid_map)."
        )

    except Exception as e:
        print(f"[BACKWARD][CALIBRATE_STORE][ERROR] {e}")


# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_track_cycle_backwards(bpy.types.Operator):
    """Frame-by-frame backward tracking with visible progress (non-blocking)."""
    bl_idname = "kaiserlich_tracker.master_track_cycle_backwards"
    bl_label = "Track Cycle Backwards (Modal)"
    bl_description = "Frame-by-frame backward tracking with visible progress (non-blocking)."
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Safety limit (0 = no limit)"
    )

    _timer = None
    _processing_names: List[str]
    _original_selected: List[str]
    _histories: Dict[str, Deque[Tuple[int, float, float]]]
    _window = None
    _area = None
    _region = None
    _space = None
    _start_frame = 0
    _end_frame = 0
    _reset_frame = 0
    _current_frame = 0
    _frames_processed = 0

    # --------------------------------------------------------
    # Initialization
    # --------------------------------------------------------

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'ERROR'}, "No active clip.")
            print("[BACKWARD][INIT] ❌ Kein aktiver Clip – Operator abgebrochen.")
            return {"CANCELLED"}

        # Determine scene start and end
        self._start_frame = scene_get_start_frame(context)
        self._end_frame = get_end_frame(context)
        if self._end_frame < self._start_frame:
            self._end_frame = self._start_frame

        # Capture selection
        self._original_selected = collect_selected_track_names(context)
        if not self._original_selected:
            self.report({'WARNING'}, "No tracks selected.")
            print("[BACKWARD][INIT] ⚠ Keine Tracks selektiert – Operator abgebrochen.")
            return {"CANCELLED"}

        self._processing_names = list(self._original_selected)

        # Find CLIP_EDITOR area
        self._window, self._area, self._region, self._space = find_clip_editor_area(clip)
        if not self._window:
            self.report({'ERROR'}, "No CLIP_EDITOR area found.")
            print("[BACKWARD][INIT] ❌ Keine CLIP_EDITOR-Area gefunden – Operator abgebrochen.")
            return {"CANCELLED"}

        # Determine playhead start position
        self._reset_frame = int(scene.frame_current)
        scene_current = int(self._reset_frame)
        if scene_current < self._start_frame:
            self._current_frame = self._start_frame
        elif scene_current > self._end_frame:
            self._current_frame = self._end_frame
        else:
            self._current_frame = scene_current

        # Set playhead
        self._space.clip_user.frame_current = int(self._current_frame)
        scene.frame_current = int(self._current_frame)

        # Initialize histories
        self._histories = {name: deque(maxlen=10) for name in self._processing_names}

        # Fix selection
        tracking = clip.tracking
        for tr in tracking.tracks:
            tr.select = (tr.name in self._original_selected)

        print(
            f"[BACKWARD][INIT] ✅ Start Frame={self._start_frame}, "
            f"End Frame={self._end_frame}, Current={self._current_frame}, "
            f"Reset={self._reset_frame}, Tracks={len(self._processing_names)}"
        )

        # --------------------------------------------------------
        # Timer starten (Modal aktivieren)
        # --------------------------------------------------------
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}
    # --------------------------------------------------------
    # Modal Loop
    # --------------------------------------------------------

    def modal(self, context, event):
        if event.type == 'ESC':
            print("[BACKWARD][MODAL] ⎋ ESC erkannt – Tracking wird abgebrochen.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        if event.type != 'TIMER':
            return {"PASS_THROUGH"}

        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            print("[BACKWARD][MODAL] ⚠ Kein aktiver Clip mehr – Operator abgebrochen.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        tracking = clip.tracking

        # Kurzer Status-Log pro Step
        print(
            f"[BACKWARD][STEP] Frame={self._current_frame}, "
            f"Aktive Tracks (vor Update)={len(self._processing_names)}"
        )

        # Update histories
        for name in list(self._processing_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(int(self._current_frame))
            if mk:
                self._histories[name].append((self._current_frame, mk.co[0], mk.co[1]))

        # --- Vor jedem Calibration-Step sichern ---
        store_calibrate_tracks_in_scene(context, self._processing_names)

        # Apply optional optimization formula
        try:
            get_from_selected_tracks_backwards(context)
            apply_formula_on_selected_tracks_backwards(context)
            print("[BACKWARD][STEP] 🔎 Formel/Optimierung für ausgewählte Tracks ausgeführt.")
        except Exception as e:
            print(f"[BACKWARD][STEP][FORMULA][ERROR] {e}")

        scene = context.scene
        best_raw = scene.get("best_tracks")
        good_raw = scene.get("good_tracks")

        def _has_tracks(val):
            if not val:
                return False
            if isinstance(val, str):
                return bool(val.strip())
            return True

        # adapt search size
        try:
            adapt_search_size_for_calibrate_tracks_backward(context)
            print("[BACKWARD][STEP] 📏 adapt_search_size_for_calibrate_tracks_backward erfolgreich.")
        except Exception as e:
            print(f"[BACKWARD][STEP][ADAPT_SEARCH][ERROR] {e}")

        # Perform backward tracking step
        success = track_markers_with_override(
            self._window, self._area, self._region, self._space,
            backwards=True, sequence=False
        )

        if not success:
            print("[BACKWARD][STEP] ❌ track_markers_with_override (backwards) fehlgeschlagen – Abbruch.")
            self._finish(context, cancelled=True)
            return {"CANCELLED"}

        # Filter active tracks
        before_filter = len(self._processing_names)
        self._processing_names, _ = filter_active_tracks_at_frame(
            context, self._processing_names, self._current_frame
        )
        after_filter = len(self._processing_names)
        print(
            f"[BACKWARD][STEP] FilterActiveTracks: vorher={before_filter}, "
            f"nachher={after_filter}"
        )

        # Exit conditions
        if not self._processing_names:
            print("[BACKWARD][EXIT] ✅ Keine aktiven Tracks mehr – Backward-Zyklus abgeschlossen.")
            self._finish(context)
            return {"FINISHED"}

        if self.max_frames > 0 and self._frames_processed >= self.max_frames:
            print(
                f"[BACKWARD][EXIT] ⏱ MaxFrames erreicht "
                f"({self._frames_processed}/{self.max_frames}) – Backward-Zyklus beendet."
            )
            self._finish(context)
            return {"FINISHED"}

        # Step backward
        scene = context.scene
        if int(self._space.clip_user.frame_current) == int(self._current_frame):
            self._space.clip_user.frame_current = int(self._current_frame) - 1

        if int(self._space.clip_user.frame_current) < int(self._start_frame):
            self._space.clip_user.frame_current = int(self._start_frame)

        scene.frame_current = int(self._space.clip_user.frame_current)
        self._current_frame = int(scene.frame_current)
        self._frames_processed += 1

        if int(self._current_frame) <= int(self._start_frame):
            print(
                f"[BACKWARD][EXIT] ⬅ Start-Frame erreicht "
                f"(Current={self._current_frame}, Start={self._start_frame}) – Backward-Zyklus beendet."
            )
            self._finish(context)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}

    # --------------------------------------------------------
    # Finalization / Cleanup
    # --------------------------------------------------------

    def _finish(self, context, cancelled: bool = False):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None

        print(
            f"[BACKWARD][FINISH] 🧾 cancelled={cancelled}, "
            f"frames_processed={self._frames_processed}"
        )

        # Restore selection
        clip = getattr(context.space_data, "clip", None)
        if clip and hasattr(clip, "tracking"):
            for tr in clip.tracking.tracks:
                tr.select = (tr.name in self._original_selected)
            print("[BACKWARD][FINISH] Selektion der ursprünglichen Tracks wiederhergestellt.")

        # Reset playhead
        try:
            reset_to_frame(context, self._reset_frame)
            print(f"[BACKWARD][FINISH] Playhead auf Frame {self._reset_frame} zurückgesetzt.")
        except Exception as e:
            print(f"[BACKWARD][FINISH][RESET_FRAME][ERROR] {e}")

        # Compute quality metrics
        try:
            from ...Helper.track_quality_metrics import compute_track_quality_metrics
            metrics = compute_track_quality_metrics(context)
            quality_percent = float(metrics.get("prozent", 100.0))
            context.scene.kaiserlich_quality_percent = f"{int(round(quality_percent))}%"
            print(f"[BACKWARD][FINISH] Qualität: {context.scene.kaiserlich_quality_percent}")

            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "CLIP_EDITOR":
                        for region in area.regions:
                            if region.type == "UI":
                                region.tag_redraw()
        except Exception as e:
            print(f"[BACKWARD][FINISH][QUALITY][ERROR] {e}")

        # Compute marker progress
        try:
            _, perc = compute_marker_progress(context.scene, update_ui=True)
            context.scene.kaiserlich_marker_progress = f"{int(round(perc))}%"
            print(f"[BACKWARD][FINISH] Marker-Progress: {context.scene.kaiserlich_marker_progress}")
        except Exception as e:
            print(f"[BACKWARD][FINISH][PROGRESS][ERROR] {e}")

        # Hand over control to forward tracking operator
        if not cancelled:
            try:
                clip = getattr(context.space_data, "clip", None)
                if clip is None:
                    print("[BACKWARD][FORWARD_HANDOVER] ⚠ Kein Clip – Forward-Zyklus wird nicht gestartet.")
                    return

                window, area, region, space = find_clip_editor_area(clip)
                if not window:
                    print("[BACKWARD][FORWARD_HANDOVER] ⚠ Keine CLIP_EDITOR-Area – Forward-Zyklus wird nicht gestartet.")
                    return

                print("[BACKWARD][FORWARD_HANDOVER] ▶ Starte forward master_track_cycle Operator.")
                with context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.kaiserlich_tracker.master_track_cycle()
            except Exception as e:
                print(f"[BACKWARD][FORWARD_HANDOVER][ERROR] {e}")


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_master_track_cycle_backwards)

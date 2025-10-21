# Operator/master_operator.py

import bpy
from typing import Any, Optional, Set, Dict, Callable, ContextManager
from contextlib import contextmanager

# Helper
from ..Helper.low_marker_frame import find_first_weak_frame
from ..Helper.filter_tracks import filter_problematic_tracks
from ..Helper.thresh_map import should_use_cached_thresholds, save_after_autocalibrate

# Handshake Keys (müssen ident mit Auto-Calibrate sein)
AC_STATUS_KEY   = "kaiserlich_ac_status"
AC_PROGRESS_KEY = "kaiserlich_ac_progress"
AC_MESSAGE_KEY  = "kaiserlich_ac_message"
AC_EPOCH_KEY    = "kaiserlich_ac_epoch"

# ---------------------------------------------------------------------------
# Context & Selection Utilities
# ---------------------------------------------------------------------------

def _find_clip_editor_area_for_clip(clip: Optional[bpy.types.MovieClip]):
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
            if not region_window:
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                if getattr(space, "clip", None) == clip or space.clip is None:
                    return window, area, region_window, space
    return None, None, None, None

def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    sd = getattr(context, "space_data", None)
    return getattr(sd, "clip", None) if sd else None

def _coerce_frame(result: Any) -> Optional[int]:
    if result is None:
        return None
    if isinstance(result, int):
        return int(result)
    if isinstance(result, (tuple, list)) and result:
        first = result[0]
        return int(first) if isinstance(first, (int, float)) else None
    return None

def _snapshot_selected_track_names(clip: Optional[bpy.types.MovieClip]) -> Set[str]:
    names: Set[str] = set()
    if not clip:
        return names
    try:
        for track in clip.tracking.tracks:
            if getattr(track, "select", False):
                names.add(track.name)
    except Exception:
        pass
    return names

def _restore_selected_tracks_by_names(clip: Optional[bpy.types.MovieClip], names: Set[str]) -> None:
    if not clip or not names:
        return
    try:
        for track in clip.tracking.tracks:
            track.select = False
        for track in clip.tracking.tracks:
            if track.name in names:
                track.select = True
    except Exception:
        pass

def _set_frame_in_scene_and_clip(context: bpy.types.Context, frame: int) -> None:
    context.scene.frame_current = int(frame)
    clip = _get_active_clip(context)
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        try:
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
                bpy.ops.clip.change_frame(frame=int(frame))
        except Exception:
            try:
                region.tag_redraw()
            except Exception:
                pass

@contextmanager
def _clip_context(context: bpy.types.Context, clip: Optional[bpy.types.MovieClip]):
    window, area, region, space = _find_clip_editor_area_for_clip(clip)
    if window and area and region and space:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space, scene=context.scene):
            yield
    else:
        yield

def _op_id(op) -> str:
    try: return op.idname()
    except Exception: return repr(op)

def _call_op_in_clip(
    op_callable,
    context: bpy.types.Context,
    clip: Optional[bpy.types.MovieClip],
    *args,
    **kwargs
) -> bool:
    """
    Führt einen Blender-Operator im CLIP_EDITOR-Kontext aus (temp_override).
    Akzeptiert Positional-Args (z. B. 'INVOKE_DEFAULT') und **kwargs.
    Erfolgreich, wenn {'FINISHED'} ODER {'RUNNING_MODAL'} zurückkommt.
    """
    try:
        with _clip_context(context, clip):
            result = op_callable(*args, **kwargs)
        if hasattr(result, "__contains__"):
            if "FINISHED" in result or "RUNNING_MODAL" in result:
                return True
        # Manche Ops liefern None → nicht fatal; wir werten das als "gestartet".
        return result is None
    except Exception as e:
        print(f"[Kaiserlich Tracker][Master] Operator-Call fehlgeschlagen: {_op_id(op_callable)} -> {e}")
        return False


# ---------------------------------------------------------------------------
# Master Operator (Modal mit Handshake)
# ---------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_operator(bpy.types.Operator):
    """Modaler Master, der Auto-Calibrate nicht-blockierend startet und dessen Fortschritt pollt."""
    bl_idname = "kaiserlich_tracker.master_operator"
    bl_label = "KAISERLICHTRACKER — Master Operator (Modal)"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    set_playhead: bpy.props.BoolProperty(
        name="Playhead setzen",
        description="Playhead im Clip Editor auf den gefundenen Frame setzen",
        default=True,
    )
    store_scene_key: bpy.props.StringProperty(
        name="Scene Key",
        description="Szenen-Property zum Ablegen des gefundenen Frames",
        default="kaiserlich_low_marker_frame",
    )
    max_iterations: bpy.props.IntProperty(
        name="Max Iterationen",
        description="Safety-Stop gegen Endlosschleifen",
        default=100,
        min=1,
        soft_min=1,
    )

    # --- interner Zustand ---
    _timer = None
    _stage = 0
    _iter = 0
    _hits = 0
    _waiting_ac = False
    _ac_epoch_expected = None
    _saved_selection: Set[str] = set()
    _current_frame: Optional[int] = None
    _clip: Optional[bpy.types.MovieClip] = None

    def _ui_ping(self, context, msg: str):
        try:
            self.report({'INFO'}, msg)
        except Exception:
            pass

    def _ac_status(self, context) -> Dict[str, Any]:
        sc = context.scene
        return {
            "status": sc.get(AC_STATUS_KEY, "IDLE"),
            "progress": float(sc.get(AC_PROGRESS_KEY, 0.0)),
            "message": sc.get(AC_MESSAGE_KEY, ""),
            "epoch": int(sc.get(AC_EPOCH_KEY, 0)),
        }

    # ---- Stage-Machine ------------------------------------------------------

    def _stage0_prepare(self, context):
        self._clip = _get_active_clip(context)
        self._saved_selection = _snapshot_selected_track_names(self._clip)
        self._ui_ping(context, "Master gestartet")
        return True

    def _stage1_find_low_marker(self, context):
        try:
            res = find_first_weak_frame(context)
            frame = _coerce_frame(res)
        except Exception as e:
            self.report({"ERROR"}, f"find_first_weak_frame() Fehler: {e}")
            return "STOP"

        if frame is None:
            self._ui_ping(context, f"Kein Low-Marker-Frame mehr. Iterationen: {self._iter}, Hits: {self._hits}")
            return "DONE"

        self._current_frame = int(frame)
        self._hits += 1
        try:
            context.scene[self.store_scene_key] = int(frame)
        except Exception:
            pass
        if self.set_playhead:
            _set_frame_in_scene_and_clip(context, frame)
        print(f"[Kaiserlich Tracker][Master] Iteration={self._iter+1} -> LowMarkerFrame={frame}")
        return True

    def _stage2_auto_calibrate_if_needed(self, context):
        # Cache/Interpolation?
        skip_auto = False
        try:
            skip_auto = should_use_cached_thresholds(context, self._current_frame)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Master] ThreshMap check failed: {e}")
            skip_auto = False

        if skip_auto:
            print("[Kaiserlich Tracker][Master] auto_calibrate SKIPPED (gespeicherte/interpolierte Thresholds).")
            return "SKIP"

        # Modal Auto-Calibrate starten
        self._ui_ping(context, "Auto-Calibrate startet …")
        prev_epoch = int(context.scene.get(AC_EPOCH_KEY, 0))
        ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.auto_calibrate, context, self._clip, 'INVOKE_DEFAULT')
        if not ok:
            # INVOKE_DEFAULT liefert oft kein {'FINISHED'}; wir akzeptieren Start best-effort
            pass
        # wir erwarten epoch = prev+1 (siehe invoke in AC-Operator)
        self._ac_epoch_expected = prev_epoch + 1
        self._waiting_ac = True
        return "WAIT"

    def _stage3_wait_for_ac(self, context):
        # Poll AC-Status
        st = self._ac_status(context)
        # Optional: Epochen-Check, damit wir auf den richtigen Lauf warten
        if st["epoch"] < (self._ac_epoch_expected or 0):
            return "WAIT"
        if st["status"] == "RUNNING":
            # UI keep-alive
            self._ui_ping(context, f"Auto-Calibrate: {int(st['progress']*100)}% — {st['message']}")
            return "WAIT"
        if st["status"] == "DONE":
            try:
                save_after_autocalibrate(context, self._current_frame, bake_neighbors=True)
            except Exception as e:
                print(f"[Kaiserlich Tracker][Master] Warnung: save_after_autocalibrate fehlgeschlagen: {e}")
            self._waiting_ac = False
            return "CONTINUE"
        if st["status"] == "ERROR":
            self.report({'WARNING'}, f"Auto-Calibrate Fehler: {st['message']}")
            self._waiting_ac = False
            return "CONTINUE"
        return "WAIT"

    def _stage4_detect_and_track(self, context):
        ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.detect_adapt, context, self._clip)
        if not ok:
            self.report({"WARNING"}, "detect_adapt fehlgeschlagen.")
        ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.track_cycle_backwards, context, self._clip)
        if not ok:
            self.report({"WARNING"}, "track_cycle_backwards fehlgeschlagen.")
        ok = _call_op_in_clip(bpy.ops.kaiserlich_tracker.track_cycle, context, self._clip)
        if not ok:
            self.report({"WARNING"}, "track_cycle (vorwärts) fehlgeschlagen.")
        _restore_selected_tracks_by_names(self._clip, self._saved_selection)

        # Cleanup-Filter nach Zyklus
        try:
            filter_problematic_tracks(context, threshold=10.0)
        except Exception as e:
            print(f"[Kaiserlich Tracker][Master] Filter Fehler: {e}")
        return True

    # ---- Blender Entry Points -----------------------------------------------

    def invoke(self, context, event):
        self._stage = 0
        self._iter = 0
        self._hits = 0
        self._waiting_ac = False
        self._ac_epoch_expected = None
        self._current_frame = None
        self._clip = _get_active_clip(context)

        # Timer für UI-Keep-Alive
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            _restore_selected_tracks_by_names(self._clip, self._saved_selection)
            self.report({'WARNING'}, "Master abgebrochen (ESC).")
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Stage-Automat
        try:
            if self._stage == 0:
                if not self._stage0_prepare(context):
                    raise RuntimeError("Init fehlgeschlagen")
                self._stage = 1
                return {'RUNNING_MODAL'}

            if self._stage == 1:
                # Safety-Stop?
                if self._iter >= max(1, int(self.max_iterations)):
                    self.report({'WARNING'}, f"Safety-Stop nach {self.max_iterations} Iterationen.")
                    raise StopIteration
                res = self._stage1_find_low_marker(context)
                if res == "DONE":
                    raise StopIteration
                if res == "STOP":
                    raise RuntimeError("Low-Marker-Suche fehlgeschlagen")
                self._stage = 2
                return {'RUNNING_MODAL'}

            if self._stage == 2:
                res = self._stage2_auto_calibrate_if_needed(context)
                if res == "SKIP":
                    self._stage = 4
                    return {'RUNNING_MODAL'}
                if res == "WAIT":
                    self._stage = 3
                    return {'RUNNING_MODAL'}
                # fallback
                self._stage = 3
                return {'RUNNING_MODAL'}

            if self._stage == 3:
                res = self._stage3_wait_for_ac(context)
                if res == "WAIT":
                    return {'RUNNING_MODAL'}
                # DONE oder ERROR -> weiter
                self._stage = 4
                return {'RUNNING_MODAL'}

            if self._stage == 4:
                self._stage4_detect_and_track(context)
                self._iter += 1
                self._stage = 1   # nächste Iteration
                return {'RUNNING_MODAL'}

        except StopIteration:
            # Fertig
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            _restore_selected_tracks_by_names(self._clip, self._saved_selection)
            self.report({'INFO'}, f"Master abgeschlossen. Iterationen={self._iter}, Hits={self._hits}")
            return {'FINISHED'}

        except Exception as e:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            _restore_selected_tracks_by_names(self._clip, self._saved_selection)
            self.report({'ERROR'}, f"Master Fehler: {e}")
            return {'CANCELLED'}

    def execute(self, context):
        return self.invoke(context, None)

# --- Registrierung ----------------------------------------------------------

classes = (KAISERLICHTRACKER_OT_master_operator,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

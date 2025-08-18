# Helper/optimize_tracking_modal.py
# Ablauf je Trial: Detect → Select@frame → Forward-Track → Score → Rollback.
# Kandidaten-Reihenfolge wie alt: Pattern → Search → Motion → Channels.
# Bewertung: primär progress_sum (neu entstandene Keyframes hinter Startframe),
# Tie-Break via error_value (kleiner besser; intern invertiert).
# Am Ende: beste Flags setzen + finaler Detect; Playhead zurück auf Ursprungsframe.

from __future__ import annotations
import bpy
from typing import Set, Tuple, Optional

__all__ = ["CLIP_OT_optimize_tracking_modal", "run_optimize_tracking_modal"]


# --------------------- Infra / Utilities --------------------------------------

def _baseline_for_selected_tracks(mc: bpy.types.MovieClip, frame: int) -> dict[int, int]:
    """
    Erstellt eine Baseline für den Fortschritt: {track_ptr: count_after_frame}
    Nur bereits AUSGEWÄHLTE Tracks (Detect hat sie exklusiv selektiert).
    """
    baseline: dict[int, int] = {}
    for tr in mc.tracking.tracks:
        if getattr(tr, "select", False):
            ptr = int(tr.as_pointer()) if hasattr(tr, "as_pointer") else id(tr)
            after = sum(1 for m in tr.markers if m.frame > frame)
            baseline[ptr] = after
    return baseline


def _log(msg: str) -> None:
    print(f"[Optimize] {msg}")

def _flush(context) -> None:
    try:
        context.view_layer.update()
    except Exception:
        pass
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

def _get_clip(context) -> Optional[bpy.types.MovieClip]:
    return getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)

def _clip_override_ctx(context):
    win = getattr(context, "window", None)
    scr = getattr(win, "screen", None) if win else None
    if not (win and scr):
        return None
    for area in scr.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "window": win,
                        "screen": scr,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                        "scene": context.scene,
                    }
    return None

def _track_ptr(tr) -> int:
    try:
        return int(tr.as_pointer())
    except Exception:
        return id(tr)

# --------------------- Snapshot / Cleanup -------------------------------------

def _snapshot_tracks_and_frame_markers(mc: bpy.types.MovieClip, frame: int) -> tuple[set[int], set[int]]:
    base_ptrs: set[int] = set()
    base_ptrs_with_marker: set[int] = set()
    for tr in mc.tracking.tracks:
        ptr = _track_ptr(tr)
        base_ptrs.add(ptr)
        if any(m.frame == frame for m in tr.markers):
            base_ptrs_with_marker.add(ptr)
    return base_ptrs, base_ptrs_with_marker

def _pretrial_sanitize_frame(mc: bpy.types.MovieClip, frame: int, base_ptrs_with_marker: set[int]) -> None:
    # Entferne prophylaktisch Marker am frame bei Tracks, die vorher dort KEINEN Marker hatten.
    for tr in mc.tracking.tracks:
        if _track_ptr(tr) not in base_ptrs_with_marker:
            for m in [m for m in tr.markers if m.frame == frame]:
                tr.markers.remove(m)

def _rollback_after_forward_track(
    mc: bpy.types.MovieClip,
    start_frame: int,
    base_ptrs: set[int],
    base_ptrs_with_marker: set[int],
) -> tuple[int, int, int]:
    """
    Rollback nach Trial:
      (a) neue Tracks (nicht in base_ptrs) → komplett löschen
      (b) auf Bestands-Tracks, die VOR Trials KEINEN Marker @start_frame hatten:
          ALLE Marker mit frame >= start_frame löschen (inkl. der Vorwärts-Tracking-Ketten)
    Rückgabe: (deleted_tracks, deleted_markers, kept_tracks)
    """
    deleted_tracks = 0
    deleted_markers = 0
    kept_tracks = 0
    tracks = mc.tracking.tracks

    # (a) neue Tracks
    for tr in list(tracks):
        if _track_ptr(tr) not in base_ptrs:
            try:
                tracks.remove(tr)
                deleted_tracks += 1
            except Exception:
                pass
        else:
            kept_tracks += 1

    # (b) Marker >= start_frame auf Bestands-Tracks ohne vorherigen Startframe-Marker
    for tr in list(tracks):
        ptr = _track_ptr(tr)
        if ptr in base_ptrs and ptr not in base_ptrs_with_marker:
            to_del = [m for m in tr.markers if m.frame >= start_frame]
            for m in to_del:
                try:
                    tr.markers.remove(m)
                    deleted_markers += 1
                except Exception:
                    pass

    return deleted_tracks, deleted_markers, kept_tracks


# --------------------- Detect / Track / Score ---------------------------------

def _set_tracker_flags(
    mc: bpy.types.MovieClip,
    pattern: int,
    search: int,
    motion_index: int,
    channel_variant: int,
) -> None:
    s = mc.tracking.settings
    # 1) Pattern/Search
    s.default_pattern_size = int(max(9, min(111, pattern)))
    s.default_search_size  = int(max(16, min(256, search)))
    s.default_margin       = s.default_search_size
    # 2) Motion-Model
    motion_models = ('Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc')
    if 0 <= motion_index < len(motion_models):
        s.default_motion_model = motion_models[motion_index]
    # 3) Channels (0:R, 1:RG, 2:G, 3:GB, 4:B)
    idx = int(channel_variant)
    s.use_default_red_channel   = (idx in (0, 1))
    s.use_default_green_channel = (idx in (1, 2, 3))
    s.use_default_blue_channel  = (idx in (3, 4))

def _try_detect(context, frame: int) -> dict:
    context.scene.frame_current = int(frame)
    # Bevorzugt neue API
    try:
        from .detect import run_detect_once  # type: ignore
        try:
            return run_detect_once(context, start_frame=int(frame), handoff_to_pipeline=False) or {}
        except TypeError:
            return run_detect_once(context, start_frame=int(frame)) or {}
    except Exception:
        pass
    # Fallback alt
    try:
        from .detect import perform_marker_detection  # type: ignore
        return perform_marker_detection(context) or {}
    except Exception:
        return {"status": "FAILED", "reason": "no_detect_impl"}

def _try_error_value(context) -> Optional[float]:
    try:
        from .error_value import error_value  # type: ignore
        return float(error_value(context))
    except Exception:
        return None

def _forward_track_current_selection(context) -> None:
    bpy.ops.clip.track_markers(backwards=False, sequence=True)

def _progress_sum_from_selected(mc: bpy.types.MovieClip, frame: int, baseline: dict[int, int]) -> int:
    progress = 0
    for tr in mc.tracking.tracks:
        if getattr(tr, "select", False):
            ptr = int(tr.as_pointer()) if hasattr(tr, "as_pointer") else id(tr)
            if ptr in baseline:
                now_after = sum(1 for m in tr.markers if m.frame > frame)
                progress += max(0, now_after - baseline[ptr])
    return int(progress)

def _trial_score_progress_then_error(mc, frame, context, baseline: dict[int, int]) -> tuple[int, float]:
    prog = _progress_sum_from_selected(mc, frame, baseline)
    try:
        from .error_value import error_value  # type: ignore
        inv_err = -float(error_value(context))
    except Exception:
        inv_err = 0.0
    return prog, inv_err

# --------------------- Kandidaten (wie alt) -----------------------------------

def _make_candidate_grid(mc: bpy.types.MovieClip) -> Tuple[list[int], list[int], list[int], list[int]]:
    s = mc.tracking.settings
    p0 = int(getattr(s, "default_pattern_size", 21)) or 21
    q0 = int(getattr(s, "default_search_size", 42)) or 42
    patt = sorted(set([max(9, p0 // 2), max(9, int(round(p0 * 0.75))), max(9, p0),
                       min(111, int(round(p0 * 1.25))), min(111, p0 * 2)]))
    sea  = sorted(set([max(16, q0 // 2), max(16, int(round(q0 * 0.75))), max(16, q0),
                       min(256, int(round(q0 * 1.25))), min(256, q0 * 2)]))
    mot  = [0, 1, 2, 3, 4, 5]
    ch   = [0, 1, 2, 3, 4]
    return patt, sea, mot, ch



# --------------------- Modal Operator -----------------------------------------

from bpy.props import BoolProperty

class CLIP_OT_optimize_tracking_modal(bpy.types.Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimize Tracking (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    # Optional: Nach Final-Detect automatisch vorwärts tracken (kannst du anlassen/abschalten)
    run_forward_track_after: BoolProperty(
        name="Run Forward Track After",
        description="Nach finalem Detect automatisch vorwärts tracken",
        default=False,
    )

    _timer = None
    _step = 0

    _start_frame: int = 0
    _mc: Optional[bpy.types.MovieClip] = None
    _base_ptrs: set[int] = set()
    _base_ptrs_with_marker: set[int] = set()
    _cands: Tuple[list[int], list[int], list[int], list[int]] | None = None

    # Indizes: Pattern → Search → Motion → Channel
    _ip = 0
    _is = 0
    _im = 0
    _ic = 0

    _best: Tuple[int, float] = (-1, float("-inf"))     # (progress_sum, -err)
    _best_cfg: Tuple[int, int, int, int] | None = None

    @classmethod
    def poll(cls, context):
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR") and _get_clip(context) is not None

    def invoke(self, context, event) -> Set[str]:
        ov = _clip_override_ctx(context)
        if not ov:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext.")
            return {'CANCELLED'}

        with bpy.context.temp_override(**ov):
            self._mc = _get_clip(bpy.context)
            if not self._mc:
                self.report({'ERROR'}, "Kein Movie Clip aktiv.")
                return {'CANCELLED'}
            self._start_frame = int(bpy.context.scene.frame_current)
            self._base_ptrs, self._base_ptrs_with_marker = _snapshot_tracks_and_frame_markers(self._mc, self._start_frame)
            self._cands = _make_candidate_grid(self._mc)

        self._ip = self._is = self._im = self._ic = 0
        self._best = (-1, float("-inf"))
        self._best_cfg = None

        wm = context.window_manager
        self._step = 0
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        _log(f"Start (frame={self._start_frame})")
        return {"RUNNING_MODAL"}

    def modal(self, context, event) -> Set[str]:
        if event.type == "ESC":
            return self._cancel(context, "ESC")
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._step == 0:
            _log("Step 0: Preflight")
            self._step = 1
            return {"RUNNING_MODAL"}

        if self._step == 1:
            done = self._run_next_trial(context)
            if done:
                self._step = 2
            return {"RUNNING_MODAL"}

        if self._step == 2:
            self._apply_best_and_finalize(context)
            return self._finish(context)

        return {"RUNNING_MODAL"}

    # --- Trials ---------------------------------------------------------------

    def _advance_indices(self) -> bool:
        patt, sea, mot, ch = self._cands
        self._ic += 1
        if self._ic >= len(ch):
            self._ic = 0
            self._im += 1
            if self._im >= len(mot):
                self._im = 0
                self._is += 1
                if self._is >= len(sea):
                    self._is = 0
                    self._ip += 1
                    if self._ip >= len(patt):
                        return True
        return False

    def _current_candidate(self) -> Tuple[int, int, int, int]:
        patt, sea, mot, ch = self._cands
        return patt[self._ip], sea[self._is], mot[self._im], ch[self._ic]

    def _run_next_trial(self, context) -> bool:
        if not self._cands:
            return True

        ov = _clip_override_ctx(context)
        if not ov:
            _log("No CLIP_EDITOR override; abort sweep.")
            return True

        with bpy.context.temp_override(**ov):
            mc = _get_clip(bpy.context)
            if not mc:
                _log("No active MovieClip; abort sweep.")
                return True

            # Ende?
            patt, sea, mot, ch = self._cands
            if self._ip >= len(patt):
                _log(f"Trials fertig. Best={self._best} cfg={self._best_cfg}")
                return True

            p, s, m, c = self._current_candidate()
            _log(f"Trial (P→S→M→C) p={p} s={s} m={m} c={c}")

            # Vorab: Frame säubern (keine Artefakte aus vorherigen Trials)
            _pretrial_sanitize_frame(mc, self._start_frame, self._base_ptrs_with_marker)

            # Flags setzen & Detect fahren
            _set_tracker_flags(mc, p, s, m, c)
            res = _try_detect(bpy.context, self._start_frame)
            _flush(bpy.context)
            st = str(res.get("status", "UNKNOWN"))
            _log(f"Detect → status={st}")

            # Detect hat die neuen Tracks exklusiv selektiert → Baseline nur von ausgewählten Tracks
            baseline_after = _baseline_for_selected_tracks(mc, self._start_frame)
            selected_tracks = len(baseline_after)
            _log(f"Selected@frame → tracks_selected={selected_tracks}")
            
            if selected_tracks > 0:
                try:
                    _forward_track_current_selection(bpy.context)  # nur vorwärts
                    _flush(bpy.context)
                    _log("ForwardTrack: OK")
                except Exception as ex:
                    _log(f"ForwardTrack FAILED: {ex}")


            # Scoring: Progress (neu hinzugekommene Marker > frame), Tie-Break error_value
            score = _trial_score_progress_then_error(mc, self._start_frame, bpy.context, baseline_after)
            _log(f"Score → progress_sum={score[0]} inv_err={score[1]}")

            # Best übernehmen?
            if (score[0] > self._best[0]) or (score[0] == self._best[0] and score[1] > self._best[1]):
                self._best = score
                self._best_cfg = (p, s, m, c)
                _log(f"→ NEW BEST {self._best} cfg={self._best_cfg}")

            # ROLLBACK: neue Tracks weg, und auf Bestands-Tracks alle Marker ab Startframe löschen
            before = len(mc.tracking.tracks)
            del_tracks, del_markers, kept = _rollback_after_forward_track(
                mc, self._start_frame, self._base_ptrs, self._base_ptrs_with_marker
            )
            after = len(mc.tracking.tracks)
            _log(f"Rollback: before={before}, removed_tracks={del_tracks}, removed_markers>={self._start_frame}:{del_markers}, kept_tracks={kept}")

            # Playhead sicherheitshalber zurück
            bpy.context.scene.frame_current = self._start_frame

        done = self._advance_indices()
        return done

    def _apply_best_and_finalize(self, context) -> None:
        if not self._best_cfg:
            _log("Keine Best-Konfiguration gefunden – nichts zu übernehmen.")
            return

        ov = _clip_override_ctx(context)
        if not ov:
            _log("Kein Override für Finalisierung.")
            return

        with bpy.context.temp_override(**ov):
            mc = _get_clip(bpy.context)
            if not mc:
                _log("Final: Kein MovieClip.")
                return

            p, s, m, c = self._best_cfg
            _log(f"Apply BEST cfg p={p} s={s} m={m} c={c}")
            _set_tracker_flags(mc, p, s, m, c)

            # Finaler Detect (bleibt bestehen)
            res = _try_detect(bpy.context, self._start_frame)
            _flush(bpy.context)
            _log(f"Final Detect status={res.get('status')}")

            # Szene-Keys (optional für Orchestrator)
            scn = bpy.context.scene
            scn["opt_best_pattern"] = p
            scn["opt_best_search"]  = s
            scn["opt_best_motion"]  = m
            scn["opt_best_channel"] = c

            # Optional: direkt im Anschluss vorwärts tracken
            if self.run_forward_track_after:
                baseline_after = _baseline_for_selected_tracks(mc, self._start_frame)
                if len(baseline_after) > 0:
                    try:
                        _forward_track_current_selection(bpy.context)
                        _flush(bpy.context)
                        _log("Final ForwardTrack: OK")
                    except Exception as ex:
                        _log(f"Final ForwardTrack FAILED: {ex}")


            # Playhead zurück
            bpy.context.scene.frame_current = self._start_frame

    # --- Lifecycle ------------------------------------------------------------

    def _finish(self, context) -> Set[str]:
        self._teardown(context)
        _log("Done.")
        return {"FINISHED"}

    def _cancel(self, context, reason: str) -> Set[str]:
        _log(f"Abbruch: {reason}")
        self._teardown(context)
        return {"CANCELLED"}

    def _teardown(self, context) -> None:
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None


# --------------------- Entry / Register ---------------------------------------

def run_optimize_tracking_modal(context: bpy.types.Context | None = None) -> None:
    try:
        bpy.ops.clip.optimize_tracking_modal("INVOKE_DEFAULT")
    except Exception as ex:
        _log(f"Fallback-Aufruf fehlgeschlagen: {ex}")

def register():
    try:
        bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass

def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass

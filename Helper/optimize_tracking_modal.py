# Helper/optimize_tracking_modal.py
# Modal-Optimierer: testet Detect-Parameter (Pattern/Search, Motion-Model, Channel-Set),
# wählt die beste Variante (MarkerCount, Tie-Break: error_value) und übernimmt sie.
# Trials werden sauber "stateless" gehalten: neue Tracks und neu entstandene Marker am Test-Frame
# werden nach jedem Trial wieder entfernt (keine Kumulierung).

from __future__ import annotations
import bpy
from typing import Set, Tuple, Optional

__all__ = ["CLIP_OT_optimize_tracking_modal", "run_optimize_tracking_modal"]


def _log(msg: str) -> None:
    print(f"[Optimize] {msg}")


def _get_clip(context) -> Optional[bpy.types.MovieClip]:
    return getattr(context.space_data, "clip", None)


def _active_marker_count(mc: bpy.types.MovieClip, frame: int) -> int:
    """Zählt Marker, die exakt auf 'frame' einen Key besitzen (sichtbar)."""
    try:
        cnt = 0
        for tr in mc.tracking.tracks:
            for m in tr.markers:
                if m.frame == frame:
                    cnt += 1
                    break
        return cnt
    except Exception:
        return 0


# --------------------- Snapshots & Cleanup (NEU) ------------------------------

def _snapshot_tracks_and_frame_markers(mc: bpy.types.MovieClip, frame: int) -> tuple[set[int], set[int]]:
    """Liefert:
    - base_ptrs: Track-Pointer vor dem Trial
    - base_ptrs_with_marker: Pointer jener Tracks, die VOR dem Trial am 'frame' einen Marker hatten
    """
    base_ptrs = set()
    base_ptrs_with_marker = set()
    for tr in mc.tracking.tracks:
        try:
            ptr = int(tr.as_pointer())
        except Exception:
            ptr = id(tr)
        base_ptrs.add(ptr)
        try:
            if any(m.frame == frame for m in tr.markers):
                base_ptrs_with_marker.add(ptr)
        except Exception:
            pass
    return base_ptrs, base_ptrs_with_marker


def _remove_new_tracks_and_frame_markers(mc: bpy.types.MovieClip,
                                         frame: int,
                                         base_ptrs: set[int],
                                         base_ptrs_with_marker: set[int]) -> tuple[int, int, int]:
    """Entfernt:
       (a) Tracks, die im Trial NEU entstanden sind (nicht in base_ptrs)
       (b) Marker am 'frame' auf bestehenden Tracks, wenn diese VOR dem Trial keinen Marker am frame hatten.
    Rückgabe: (deleted_tracks, deleted_markers, kept_tracks)
    """
    deleted_tracks = 0
    deleted_markers = 0
    kept_tracks = 0
    tracks = mc.tracking.tracks

    # 1) Neue Tracks komplett löschen
    for tr in list(tracks):
        try:
            ptr = int(tr.as_pointer())
        except Exception:
            ptr = id(tr)
        if ptr not in base_ptrs:
            try:
                tracks.remove(tr)
                deleted_tracks += 1
            except Exception:
                pass
        else:
            kept_tracks += 1

    # 2) Auf bestehenden Tracks: Marker am frame löschen, falls es vor dem Trial dort keinen gab
    for tr in list(tracks):
        try:
            ptr = int(tr.as_pointer())
        except Exception:
            ptr = id(tr)
        if ptr in base_ptrs:
            had_marker_before = ptr in base_ptrs_with_marker
            if not had_marker_before:
                try:
                    ms = [m for m in tr.markers if m.frame == frame]
                    for m in ms:
                        try:
                            tr.markers.remove(m)
                            deleted_markers += 1
                        except Exception:
                            pass
                except Exception:
                    pass

    return deleted_tracks, deleted_markers, kept_tracks


def _pretrial_sanitize_frame(mc: bpy.types.MovieClip,
                             frame: int,
                             base_ptrs_with_marker: set[int]) -> None:
    """Idempotent: löscht vorsorglich Marker am frame auf Tracks, die vorher dort keinen Marker hatten."""
    for tr in mc.tracking.tracks:
        try:
            ptr = int(tr.as_pointer())
        except Exception:
            ptr = id(tr)
        if ptr not in base_ptrs_with_marker:
            try:
                for m in [m for m in tr.markers if m.frame == frame]:
                    tr.markers.remove(m)
            except Exception:
                pass


# --------------------- Detect & Scoring --------------------------------------

def _set_tracker_flags(mc: bpy.types.MovieClip,
                       pattern: int,
                       search: int,
                       motion_index: int,
                       channel_variant: int) -> None:
    """Schreibt Pattern/Search/Motion/Channel-Flags in tracking.settings."""
    s = mc.tracking.settings
    s.default_pattern_size = int(max(9, min(111, pattern)))
    s.default_search_size = int(max(16, min(256, search)))
    s.default_margin = s.default_search_size

    motion_models = ('Perspective', 'Affine', 'LocRotScale', 'LocScale', 'LocRot', 'Loc')
    if 0 <= motion_index < len(motion_models):
        s.default_motion_model = motion_models[motion_index]

    # Farbkanal-Varianten: 0:R, 1:RG, 2:G, 3:GB, 4:B
    idx = int(channel_variant)
    s.use_default_red_channel   = (idx in (0, 1))
    s.use_default_green_channel = (idx in (1, 2, 3))
    s.use_default_blue_channel  = (idx in (3, 4))


def _try_detect(context, frame: int) -> dict:
    """Versucht run_detect_once, fallback perform_marker_detection. Rückgabe: dict mit status."""
    try:
        context.scene.frame_current = int(frame)
    except Exception:
        pass

    try:
        from .detect import run_detect_once  # type: ignore
        try:
            res = run_detect_once(context, start_frame=int(frame), handoff_to_pipeline=False) or {}
        except TypeError:
            res = run_detect_once(context, start_frame=int(frame)) or {}
        return res if isinstance(res, dict) else {"status": "UNKNOWN"}
    except Exception:
        pass

    try:
        from .detect import perform_marker_detection  # type: ignore
        res2 = perform_marker_detection(context) or {}
        return res2 if isinstance(res2, dict) else {"status": "UNKNOWN"}
    except Exception:
        return {"status": "FAILED", "reason": "no_detect_impl"}


def _try_error_value(context) -> Optional[float]:
    """Optionaler Tie-Breaker: kleiner ist besser. Falls nicht verfügbar → None."""
    try:
        from .error_value import error_value  # type: ignore
        v = error_value(context)
        return float(v)
    except Exception:
        return None


def _trial_score(mc: bpy.types.MovieClip, frame: int, context) -> Tuple[int, float]:
    """Score: (marker_count DESC, -error ASC via invert)."""
    cnt = _active_marker_count(mc, frame)
    err = _try_error_value(context)
    inv_err = -float(err) if (err is not None) else 0.0
    return cnt, inv_err


def _make_candidate_grid(mc: bpy.types.MovieClip) -> Tuple[list[int], list[int], list[int], list[int]]:
    """Baut Kandidatenlisten um aktuelle Defaults herum (defensiv begrenzt)."""
    s = mc.tracking.settings
    p0 = int(getattr(s, "default_pattern_size", 21)) or 21
    q0 = int(getattr(s, "default_search_size", 42)) or 42

    patt = sorted(set([
        max(9,  p0 // 2),
        max(9,  int(round(p0 * 0.75))),
        max(9,  p0),
        min(111, int(round(p0 * 1.25))),
        min(111, p0 * 2),
    ]))

    sea = sorted(set([
        max(16,  q0 // 2),
        max(16,  int(round(q0 * 0.75))),
        max(16,  q0),
        min(256, int(round(q0 * 1.25))),
        min(256, q0 * 2),
    ]))

    mot = [0, 1, 2, 3, 4, 5]  # Motion-Models
    ch  = [0, 1, 2, 3, 4]     # Channel-Sets

    return patt, sea, mot, ch


# --------------------- Modal Operator ----------------------------------------

class CLIP_OT_optimize_tracking_modal(bpy.types.Operator):
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimize Tracking (Modal)"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _step = 0

    # State
    _frame: int = 0
    _mc: Optional[bpy.types.MovieClip] = None
    _base_ptrs: set[int] = set()
    _base_ptrs_with_marker: set[int] = set()
    _cands: Tuple[list[int], list[int], list[int], list[int]] | None = None
    _idxs = (0, 0, 0, 0)  # laufende Indizes (p, s, m, c)
    _best: Tuple[int, float] = (-1, float("-inf"))  # (count, -err)
    _best_cfg: Tuple[int, int, int, int] | None = None

    @classmethod
    def poll(cls, context):
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR") and _get_clip(context) is not None

    def _log(self, msg: str) -> None:
        _log(msg)

    def invoke(self, context, event) -> Set[str]:
        self._mc = _get_clip(context)
        if not self._mc:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        self._frame = int(context.scene.frame_current)
        self._base_ptrs, self._base_ptrs_with_marker = _snapshot_tracks_and_frame_markers(self._mc, self._frame)
        self._cands = _make_candidate_grid(self._mc)
        self._idxs = (0, 0, 0, 0)
        self._best = (-1, float("-inf"))
        self._best_cfg = None

        wm = context.window_manager
        self._step = 0
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        self._log(f"Start (frame={self._frame})")
        return {"RUNNING_MODAL"}

    def modal(self, context, event) -> Set[str]:
        if event.type == "ESC":
            return self._cancel(context, "ESC")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._step == 0:
            self._log("Step 0: Preflight")
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

    # --- Sweep-Engine ---------------------------------------------------------
    def _run_next_trial(self, context) -> bool:
        assert self._mc is not None and self._cands is not None
        patt, sea, mot, ch = self._cands
        ip, is_, im, ic = self._idxs

        if ip >= len(patt):
            self._log(f"Trials fertig. Best={self._best} cfg={self._best_cfg}")
            return True

        p = patt[ip]; s = sea[is_]; m = mot[im]; c = ch[ic]
        self._log(f"Trial p={p} s={s} m={m} c={c}")

        # Vorsorglich Frame bereinigen (idempotent)
        _pretrial_sanitize_frame(self._mc, self._frame, self._base_ptrs_with_marker)

        _set_tracker_flags(self._mc, p, s, m, c)

        res = _try_detect(context, self._frame)
        st = str(res.get("status", "UNKNOWN"))
        self._log(f"Detect → status={st}")

        score = _trial_score(self._mc, self._frame, context)
        self._log(f"Score → count={score[0]} inv_err={score[1]}")

        if (score[0] > self._best[0]) or (score[0] == self._best[0] and score[1] > self._best[1]):
            self._best = score
            self._best_cfg = (p, s, m, c)
            self._log(f"→ NEW BEST {self._best} cfg={self._best_cfg}")

        # Cleanup: neue Tracks + neu entstandene Marker am Frame entfernen
        del_tracks, del_markers, kept = _remove_new_tracks_and_frame_markers(
            self._mc, self._frame, self._base_ptrs, self._base_ptrs_with_marker
        )
        self._log(f"Cleanup: removed_tracks={del_tracks}, removed_markers_at_frame={del_markers}, kept_tracks={kept}")

        # Indizes weiterschalten (nested loops)
        ic += 1
        if ic >= len(ch):
            ic = 0
            im += 1
            if im >= len(mot):
                im = 0
                is_ += 1
                if is_ >= len(sea):
                    is_ = 0
                    ip += 1
        self._idxs = (ip, is_, im, ic)
        return False

    def _apply_best_and_finalize(self, context) -> None:
        if not self._mc or not self._best_cfg:
            self._log("Keine Best-Konfiguration gefunden – nichts zu übernehmen.")
            return

        p, s, m, c = self._best_cfg
        self._log(f"Apply BEST cfg p={p} s={s} m={m} c={c}")
        _set_tracker_flags(self._mc, p, s, m, c)

        res = _try_detect(context, self._frame)
        self._log(f"Final Detect status={res.get('status')}")

    # --- Lifecycle ------------------------------------------------------------
    def _finish(self, context) -> Set[str]:
        self._teardown(context)
        self._log("Done.")
        return {"FINISHED"}

    def _cancel(self, context, reason: str) -> Set[str]:
        self._log(f"Abbruch: {reason}")
        self._teardown(context)
        return {"CANCELLED"}

    def _teardown(self, context) -> None:
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None


def run_optimize_tracking_modal(context: bpy.types.Context | None = None) -> None:
    """Fallback-Aufruf: startet den Modal-Operator (wie INVOKE_DEFAULT)."""
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

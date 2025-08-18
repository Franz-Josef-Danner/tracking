# Helper/optimize_tracking_modal.py
# Modal-Optimierer mit alter Reihenfolge: Pattern/Search → Motion-Model → Channels
# Trials sind stateless: Nach jedem Versuch werden neu entstandene Tracks
# und Marker am Test-Frame wieder entfernt. Scoring wie alt:
# 1) MarkerCount (DESC), 2) Tie-Break via error_value (ASC).
# Finale Aktion: Gewinner-Setup setzen + EIN finaler Detect (kein Cleanup danach).

from __future__ import annotations
import bpy
from typing import Set, Tuple, Optional

__all__ = ["CLIP_OT_optimize_tracking_modal", "run_optimize_tracking_modal"]


# --------------------- Infra / Utilities --------------------------------------

def _log(msg: str) -> None:
    print(f"[Optimize] {msg}")

def _flush(context) -> None:
    """Depsgraph/UI refresh, damit RNA-Änderungen sichtbar werden."""
    try:
        context.view_layer.update()
    except Exception:
        pass
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass

def _get_clip(context) -> Optional[bpy.types.MovieClip]:
    """Bevorzugt den Edit-MovieClip des CLIP_EDITOR; Fallback auf space_data.clip."""
    return getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)

def _clip_override_ctx(context):
    """Sicherer Override für aktiven CLIP_EDITOR (falls vorhanden)."""
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


# --------------------- Snapshot / Cleanup -------------------------------------

def _track_ptr(tr) -> int:
    try:
        return int(tr.as_pointer())
    except Exception:
        return id(tr)

def _snapshot_tracks_and_frame_markers(mc: bpy.types.MovieClip, frame: int) -> tuple[set[int], set[int]]:
    """
    base_ptrs: alle Track-Pointer VOR Trials
    base_ptrs_with_marker: jene Tracks, die VOR Trials am 'frame' bereits Marker hatten
    """
    base_ptrs: set[int] = set()
    base_ptrs_with_marker: set[int] = set()
    for tr in mc.tracking.tracks:
        ptr = _track_ptr(tr)
        base_ptrs.add(ptr)
        try:
            if any(m.frame == frame for m in tr.markers):
                base_ptrs_with_marker.add(ptr)
        except Exception:
            pass
    return base_ptrs, base_ptrs_with_marker

def _pretrial_sanitize_frame(mc: bpy.types.MovieClip, frame: int, base_ptrs_with_marker: set[int]) -> None:
    """
    Idempotent: Entfernt vorsorglich Marker am frame auf Tracks, die vorher dort KEINEN Marker hatten.
    So wird verhindert, dass ein vorangegangenes Trial Artefakte hinterlässt.
    """
    for tr in mc.tracking.tracks:
        if _track_ptr(tr) not in base_ptrs_with_marker:
            try:
                for m in [m for m in tr.markers if m.frame == frame]:
                    tr.markers.remove(m)
            except Exception:
                pass

def _remove_new_tracks_and_frame_markers(
    mc: bpy.types.MovieClip,
    frame: int,
    base_ptrs: set[int],
    base_ptrs_with_marker: set[int],
) -> tuple[int, int, int]:
    """
    Rollback nach JEDEM Trial:
    (a) Löscht neu entstandene Tracks (nicht in base_ptrs).
    (b) Löscht Marker am frame von Bestands-Tracks, wenn diese VOR Trials am frame KEINEN Marker hatten.
    Rückgabe: (deleted_tracks, deleted_markers, kept_tracks)
    """
    deleted_tracks = 0
    deleted_markers = 0
    kept_tracks = 0
    tracks = mc.tracking.tracks

    # 1) Neue Tracks entfernen
    for tr in list(tracks):
        if _track_ptr(tr) not in base_ptrs:
            try:
                tracks.remove(tr)
                deleted_tracks += 1
            except Exception:
                pass
        else:
            kept_tracks += 1

    # 2) Neue Marker am 'frame' auf Bestands-Tracks entfernen
    for tr in list(tracks):
        ptr = _track_ptr(tr)
        if ptr in base_ptrs and ptr not in base_ptrs_with_marker:
            try:
                for m in [m for m in tr.markers if m.frame == frame]:
                    tr.markers.remove(m)
                    deleted_markers += 1
            except Exception:
                pass

    return deleted_tracks, deleted_markers, kept_tracks


# --------------------- Detect & Scoring ---------------------------------------

def _set_tracker_flags(
    mc: bpy.types.MovieClip,
    pattern: int,
    search: int,
    motion_index: int,
    channel_variant: int,
) -> None:
    """
    Schreibt Flags in tracking.settings (Pattern/Search/Motion/Channels).
    Reihenfolge (kompatibel zur alten Logik):
    1) Pattern/Search
    2) Motion-Model
    3) Channel-Set
    """
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
    """Primär run_detect_once(..., handoff_to_pipeline=False), Fallback perform_marker_detection()."""
    try:
        context.scene.frame_current = int(frame)
    except Exception:
        pass

    # Neuer Pfad
    try:
        from .detect import run_detect_once  # type: ignore
        try:
            res = run_detect_once(context, start_frame=int(frame), handoff_to_pipeline=False) or {}
        except TypeError:
            # Alte Signatur ohne handoff_to_pipeline
            res = run_detect_once(context, start_frame=int(frame)) or {}
        return res if isinstance(res, dict) else {"status": "UNKNOWN"}
    except Exception:
        pass

    # Fallback (alt)
    try:
        from .detect import perform_marker_detection  # type: ignore
        res2 = perform_marker_detection(context) or {}
        return res2 if isinstance(res2, dict) else {"status": "UNKNOWN"}
    except Exception:
        return {"status": "FAILED", "reason": "no_detect_impl"}

def _try_error_value(context) -> Optional[float]:
    """Tie-Breaker wie alt: kleiner ist besser. Optional."""
    try:
        from .error_value import error_value  # type: ignore
        v = error_value(context)
        return float(v)
    except Exception:
        return None

def _trial_score(mc: bpy.types.MovieClip, frame: int, context) -> Tuple[int, float]:
    """
    Scoring wie alt:
    - Primär MarkerCount (DESC)
    - Tie-Break via error_value (ASC) → wir invertieren (negativ) für einfacheren Vergleich.
    """
    cnt = _active_marker_count(mc, frame)
    err = _try_error_value(context)
    inv_err = -float(err) if (err is not None) else 0.0
    return cnt, inv_err


# --------------------- Kandidaten (Reihenfolge wie alt) -----------------------

def _make_candidate_grid(mc: bpy.types.MovieClip) -> Tuple[list[int], list[int], list[int], list[int]]:
    """
    Baut Kandidatenlisten um aktuelle Defaults.
    Reihenfolge: Pattern/Search → Motion → Channels (wie alt).
    """
    s = mc.tracking.settings
    p0 = int(getattr(s, "default_pattern_size", 21)) or 21
    q0 = int(getattr(s, "default_search_size", 42)) or 42

    # Pattern/Search nah an Defaults, in beide Richtungen
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

    # Motion-Model: alt → Index 0..5
    mot = [0, 1, 2, 3, 4, 5]

    # Channels zuletzt
    ch  = [0, 1, 2, 3, 4]

    return patt, sea, mot, ch


# --------------------- Modal Operator -----------------------------------------

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

    # Laufende Indizes entsprechend alter Reihenfolge:
    # pattern → search → motion → channel
    _ip = 0
    _is = 0
    _im = 0
    _ic = 0

    _best: Tuple[int, float] = (-1, float("-inf"))  # (count, -err)
    _best_cfg: Tuple[int, int, int, int] | None = None

    @classmethod
    def poll(cls, context):
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR") and _get_clip(context) is not None

    def invoke(self, context, event) -> Set[str]:
        self._mc = _get_clip(context)
        if not self._mc:
            self.report({'ERROR'}, "Kein Movie Clip aktiv.")
            return {'CANCELLED'}

        self._frame = int(context.scene.frame_current)
        self._base_ptrs, self._base_ptrs_with_marker = _snapshot_tracks_and_frame_markers(self._mc, self._frame)
        self._cands = _make_candidate_grid(self._mc)

        # Reset Indizes / Resultate
        self._ip = self._is = self._im = self._ic = 0
        self._best = (-1, float("-inf"))
        self._best_cfg = None

        wm = context.window_manager
        self._step = 0
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        _log(f"Start (frame={self._frame})")
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

    # --- Trial-Engine (exakt: Pattern → Search → Motion → Channel) ------------

    def _advance_indices(self) -> bool:
        """Verschachtelte Indizes in alter Reihenfolge weiterdrehen.
        Rückgabe: True = alle Trials erledigt.
        """
        assert self._cands is not None
        patt, sea, mot, ch = self._cands

        # Innerste Dimension: Channels
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
        assert self._cands is not None
        patt, sea, mot, ch = self._cands
        return patt[self._ip], sea[self._is], mot[self._im], ch[self._ic]

    def _run_next_trial(self, context) -> bool:
        if self._cands is None or self._mc is None:
            return True  # nichts zu tun

        # Ende erreicht?
        patt, sea, mot, ch = self._cands
        if self._ip >= len(patt):
            _log(f"Trials fertig. Best={self._best} cfg={self._best_cfg}")
            return True

        p, s, m, c = self._current_candidate()
        _log(f"Trial (order=Pattern→Search→Motion→Channels) p={p} s={s} m={m} c={c}")

        # Vorsorgliche Sanitisierung am Testframe (idempotent)
        override = _clip_override_ctx(context)
        if override:
            with bpy.context.temp_override(**override):
                _pretrial_sanitize_frame(self._mc, self._frame, self._base_ptrs_with_marker)
        else:
            _pretrial_sanitize_frame(self._mc, self._frame, self._base_ptrs_with_marker)

        # Flags setzen in alter Reihenfolge und Detect fahren (Tracking-Versuch)
        _set_tracker_flags(self._mc, p, s, m, c)
        res = _try_detect(context, self._frame)
        _flush(context)
        _log(f"Detect → status={str(res.get('status', 'UNKNOWN'))}")

        # Scoring (MarkerCount / error_value)
        score = _trial_score(self._mc, self._frame, context)
        _log(f"Score → count={score[0]} inv_err={score[1]}")

        # Bestes Ergebnis übernehmen
        if (score[0] > self._best[0]) or (score[0] == self._best[0] and score[1] > self._best[1]):
            self._best = score
            self._best_cfg = (p, s, m, c)
            _log(f"→ NEW BEST {self._best} cfg={self._best_cfg}")

        # ROLLBACK NACH DEM TRACKING-VERSUCH (kein Summieren von Markern/Tracks)
        if override:
            with bpy.context.temp_override(**override):
                del_tracks, del_markers, kept = _remove_new_tracks_and_frame_markers(
                    self._mc, self._frame, self._base_ptrs, self._base_ptrs_with_marker
                )
        else:
            del_tracks, del_markers, kept = _remove_new_tracks_and_frame_markers(
                self._mc, self._frame, self._base_ptrs, self._base_ptrs_with_marker
            )
        _log(f"Rollback: removed_tracks={del_tracks}, removed_markers_at_frame={del_markers}, kept_tracks={kept}")

        # Nächste Kandidaten-Kombi (alter Reihenfolge folgend)
        done = self._advance_indices()
        return done

    def _apply_best_and_finalize(self, context) -> None:
        """Gewinner-Setup setzen + finalen Detect ausführen (bleibt bestehen)."""
        if not self._mc or not self._best_cfg:
            _log("Keine Best-Konfiguration gefunden – nichts zu übernehmen.")
            return
        p, s, m, c = self._best_cfg
        _log(f"Apply BEST cfg p={p} s={s} m={m} c={c}")
        _set_tracker_flags(self._mc, p, s, m, c)
        res = _try_detect(context, self._frame)
        _flush(context)
        _log(f"Final Detect status={res.get('status')}")

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


# --------------------- Fallback-Entry & (De-)Register -------------------------

def run_optimize_tracking_modal(context: bpy.types.Context | None = None) -> None:
    """Convenience-Entry: startet Modal-Operator wie INVOKE_DEFAULT."""
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

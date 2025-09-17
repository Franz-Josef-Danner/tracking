from __future__ import annotations
import bpy
from typing import Iterable, Optional

__all__ = ("solve_camera_only",)

# --- helpers ---------------------------------------------------------------
def _resolve_clip(context) -> Optional[bpy.types.MovieClip]:
    sp = getattr(context, "space_data", None)
    if sp and getattr(sp, "type", None) == 'CLIP_EDITOR':
        return getattr(sp, "clip", None)
    try:
        return bpy.data.movieclips[0]
    except Exception:
        return None

def _clip_end_for_scene(clip: bpy.types.MovieClip, scn: bpy.types.Scene) -> int:
    try:
        start = int(getattr(clip, "frame_start", 1))
        dur   = int(getattr(clip, "frame_duration", 0))
        c_end = start + max(0, dur - 1)
    except Exception:
        c_end = int(getattr(scn, "frame_end", 1))
    return min(int(getattr(scn, "frame_end", 1)), int(c_end))

def _clamp_view_to_range(
    scn: Optional[bpy.types.Scene],
    clip: Optional[bpy.types.MovieClip],
    *,
    spaces: Iterable[Optional[bpy.types.Space]] = (),
) -> None:
    """Clamp Scene/Viewer auf Clip/Szenen-Ende (prä-Solve)."""

    if scn is None or clip is None:
        return

    try:
        end = _clip_end_for_scene(clip, scn)
    except Exception:
        return

    try:
        cur = int(getattr(scn, "frame_current", end))
        if cur > end:
            print(f"[SolveGuard] clamp scene.frame_current {cur} → {end}")
            scn.frame_current = end
    except Exception:
        pass

    for space in spaces:
        if not space or getattr(space, "type", None) != 'CLIP_EDITOR':
            continue
        try:
            clip_user = getattr(space, "clip_user", None)
            if clip_user is None:
                continue
            cu_frame = int(getattr(clip_user, "frame_current", end))
            if cu_frame > end:
                clip_user.frame_current = end
        except Exception:
            pass

def _clamp_to_solved_range_post(
    scn: Optional[bpy.types.Scene],
    clip: Optional[bpy.types.MovieClip],
    *,
    spaces: Iterable[Optional[bpy.types.Space]] = (),
) -> None:
    """Nach Solve: auf max tatsächlich gelösten Kameraframe clampen."""

    if scn is None or clip is None:
        return

    try:
        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            return
        cams = []
        recon_main = getattr(tracking, "reconstruction", None)
        if recon_main:
            cams.extend(getattr(recon_main, "cameras", []) or [])
        for obj in getattr(tracking, "objects", []):
            recon_obj = getattr(obj, "reconstruction", None)
            if recon_obj:
                cams.extend(getattr(recon_obj, "cameras", []) or [])
        frames = []
        for cam in cams:
            try:
                frame = getattr(cam, "frame", None)
                if frame is None:
                    continue
                frames.append(int(frame))
            except Exception:
                continue
        if not frames:
            return
        max_cam = max(frames)
        cur = int(getattr(scn, "frame_current", max_cam))
        if cur > max_cam:
            print(f"[SolveGuard] clamp to solved max {max_cam} from {cur}")
            scn.frame_current = max_cam
        for space in spaces:
            if not space or getattr(space, "type", None) != 'CLIP_EDITOR':
                continue
            try:
                clip_user = getattr(space, "clip_user", None)
                if clip_user is None:
                    continue
                cu_frame = int(getattr(clip_user, "frame_current", max_cam))
                if cu_frame > max_cam:
                    clip_user.frame_current = max_cam
            except Exception:
                pass
    except Exception:
        pass
# -- interne Hilfe: passenden CLIP_EDITOR im aktuellen Window finden ---------

def _find_clip_window(context) -> tuple[Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]]:
    win = getattr(context, "window", None)
    screen = getattr(win, "screen", None)
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


# -- öffentliche API ----------------------------------------------------------

def solve_camera_only(context):
    """Löst nur den Kamera-Solve aus – kein Cleanup, kein Warten.

    Versucht, falls möglich, einen Kontext-Override auf einen CLIP_EDITOR zu
    setzen, damit der Operator zuverlässig läuft. Fällt ansonsten auf den
    globalen Kontext zurück.

    Returns
    -------
    set | dict
        Das Operator-Resultat (z. B. {'RUNNING_MODAL'} oder {'CANCELLED'}).
    """
    area, region, space = _find_clip_window(context)
    scn = getattr(context, "scene", None)
    clip = _resolve_clip(context)
    if clip is None and space is not None:
        clip = getattr(space, "clip", None)
    spaces: list[Optional[bpy.types.Space]] = []
    for candidate in (getattr(context, "space_data", None), space):
        if candidate and getattr(candidate, "type", None) == 'CLIP_EDITOR':
            if candidate not in spaces:
                spaces.append(candidate)
    _clamp_view_to_range(scn, clip, spaces=spaces)
    try:
        if area and region and space:
            with context.temp_override(area=area, region=region, space_data=space):
                res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            _clamp_to_solved_range_post(scn, clip, spaces=spaces)
            return res
        res = bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        _clamp_to_solved_range_post(scn, clip, spaces=spaces)
        return res
    except Exception as e:
        return {"CANCELLED"}


# ----------------------------------------------------------------------------
# HINWEIS FÜR DEN KOORDINATOR (separate Datei!):
#
# In Operator/tracking_coordinator.py oben importieren:
#     from ..Helper.solve_camera import solve_camera_only
#
# Und in der State-Methode den Solve auslösen (ohne Diff-Marker!):
#
#     def _state_solve(self, context):
#         """Startet ausschließlich den Kamera-Solve und wechselt in SOLVE_WAIT."""
#         try:
#             res = solve_camera_only(context)
#             print(f"[Coord] Solve invoked: {res}")
#         except Exception as ex:
#             print(f"[Coord] SOLVE start failed: {ex!r}")
#             self._state = "FINALIZE"
#             return {'RUNNING_MODAL'}
#
#         self._state = "SOLVE_WAIT"
#         return {'RUNNING_MODAL'}
# ----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Ergänzung für Operator/tracking_coordinator.py: _state_solve_wait()
# -----------------------------------------------------------------------------
# Füge diese Methode in die Klasse CLIP_OT_tracking_coordinator ein.
# Sie wartet kurz auf eine gültige Reconstruction, bewertet den Solve-Error
# und triggert optional den Refine-Modal. Bei Erfolg → FINALIZE.

# --- BEGIN PASTE ---
    def _state_solve_wait(self, context):
        """Wartet auf gültige Reconstruction, bewertet Solve-Error, entscheidet Pfad."""
        # Falls nicht gesetzt (z. B. bei direktem Einstieg), initialisieren:
        if int(getattr(self, "_solve_wait_ticks", 0)) <= 0:
            self._solve_wait_ticks = int(getattr(context.scene, "solve_wait_ticks", _SOLVE_WAIT_TICKS_DEFAULT))
    
        # Pro Timer-Tick nur kurz warten, damit UI reaktiv bleibt
        ready = _wait_for_reconstruction(context, tries=_SOLVE_WAIT_TRIES_PER_TICK)
        if ready:
            err = _compute_solve_error(context)
    
            if err is None:
                # Keine auswertbare Qualität → Fehlpfad
                return self._handle_failed_solve(context)
    
            # Schwelle aus Scene-Property (Fallback: 20.0, wie in deinem Flow)
            thr = float(getattr(context.scene, "refine_threshold", 20.0) or 20.0)
    
            # Optionaler Refine nach Solve (nur einmal)
            if (not self._post_solve_refine_done) and (err > thr):
                self._launch_refine(context, threshold=thr)
                return {"RUNNING_MODAL"}
    
            # Solve ok → fertig
            self._state = "FINALIZE"
            return {"RUNNING_MODAL"}
    
        # Noch nicht ready → Countdown
        self._solve_wait_ticks = max(0, int(self._solve_wait_ticks) - 1)
        if self._solve_wait_ticks <= 0:
            return self._handle_failed_solve(context)
    
        return {"RUNNING_MODAL"}


# --- END PASTE ---

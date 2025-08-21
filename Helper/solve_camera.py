from __future__ import annotations

"""
solve_camera.py — Orchestrator for camera solving + projection cleanup (builtin)

Fixes included:
- Run builtin projection cleanup inside a guaranteed CLIP_EDITOR context
- Use 'resolve_error' (per process spec) as the threshold key for cleanup
- Post-clean signal to Coordinator when cleanup affected tracks OR when
  camera coverage has gaps (e.g., "No camera for frame …")
- Cleaner logging, PEP 8 formatting

This module assumes that another part of the pipeline stores an error
threshold in scene["resolve_error"]. If it's missing, we fall back to
current solve average error.
"""

import bpy
from typing import Optional, Tuple, Set

# Keep import (side-effect: ensure helper is loaded; do not remove)
from .refine_high_error import run_refine_on_high_error  # noqa: F401
from .projection_cleanup_builtin import (
    builtin_projection_cleanup,
    find_clip_window,
)

__all__ = (
    "solve_watch_clean",
    "run_solve_watch_clean",
)


# ---------------------------------------------------------------------------
# Context & helper utilities
# ---------------------------------------------------------------------------

def _find_clip_window(context: bpy.types.Context) -> Tuple[
    Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]
]:
    """Return an area/region/space triple for the CLIP_EDITOR if available."""
    win = context.window
    if not win or not getattr(win, "screen", None):
        return None, None, None
    for area in win.screen.areas:
        if area.type == "CLIP_EDITOR":
            region_window = None
            for r in area.regions:
                if r.type == "WINDOW":
                    region_window = r
                    break
            if region_window:
                return area, region_window, area.spaces.active
    return None, None, None


def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _get_reconstruction(
    context: bpy.types.Context,
) -> Tuple[Optional[bpy.types.MovieClip], Optional[object]]:
    clip = _get_active_clip(context)
    if not clip:
        return None, None
    obj = clip.tracking.objects.active
    return clip, obj.reconstruction


def _solve_once(context: bpy.types.Context, *, label: str = "") -> float:
    """Run the Blender solve operator and return the reconstruction avg error."""
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("No CLIP_EDITOR window found (context required).")

    with context.temp_override(area=area, region=region, space_data=space):
        res = bpy.ops.clip.solve_camera("INVOKE_DEFAULT")
        if res != {"FINISHED"}:
            raise RuntimeError("Solve failed or was cancelled.")

    _, recon = _get_reconstruction(context)
    avg = float(getattr(recon, "average_error", 0.0)) if (recon and recon.is_valid) else 0.0
    print(f"[SolveWatch] Solve {label or ''} OK (AvgErr={avg:.6f}).")
    return avg


def _compute_camera_coverage(
    clip: Optional[bpy.types.MovieClip],
    recon: Optional[object],
) -> dict:
    """Best-effort coverage heuristic over reconstructed cameras.

    Returns a dict with:
      - has_gap: bool
      - first_cam: Optional[int]
      - last_cam: Optional[int]
      - clip_start: Optional[int]
      - clip_end: Optional[int]
    """
    result = {
        "has_gap": False,
        "first_cam": None,
        "last_cam": None,
        "clip_start": None,
        "clip_end": None,
    }

    if not clip or not recon or not getattr(recon, "is_valid", False):
        return result

    cams: Set[int] = set()
    try:
        for c in getattr(recon, "cameras", []):  # MovieTrackingReconstructedCameras
            frame = getattr(c, "frame", None)
            if isinstance(frame, int):
                cams.add(frame)
    except Exception:
        pass

    if not cams:
        return result

    first_cam = min(cams)
    last_cam = max(cams)
    # MovieClip frame_start / frame_duration are defined in clip space
    clip_start = int(getattr(clip, "frame_start", 1))
    clip_end = clip_start + int(getattr(clip, "frame_duration", 0)) - 1

    result.update(
        {
            "first_cam": first_cam,
            "last_cam": last_cam,
            "clip_start": clip_start,
            "clip_end": clip_end,
            "has_gap": (first_cam > clip_start + 1) or (last_cam < clip_end - 1),
        }
    )
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def solve_watch_clean(
    context: bpy.types.Context,
    *,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Solve, store errors, run builtin projection cleanup, and signal Coordinator.

    Steps
    -----
    1) Run camera solve (INVOKE_DEFAULT)
    2) Read solve average error and persist to scene['solve_error']
    3) Determine cleanup threshold using scene['resolve_error'] (spec) or fallback
       to current solve average if missing
    4) Run builtin projection cleanup inside a guaranteed CLIP_EDITOR context
    5) If tracks were affected or coverage has gaps, set post-clean flags for the
       Coordinator to loop back to FIND_LOW / tracking
    """
    scene = context.scene

    # --- 0) Ensure CLIP context/clip is available ---
    area, region, space = find_clip_window(context)
    if not area or not space or not getattr(space, "clip", None):
        print("[SolveWatch] ERROR: No active Movie Clip in CLIP_EDITOR found.")
        return {"CANCELLED"}

    clip = space.clip

    # --- 1) Solve camera ---
    print("[SolveWatch] Starting camera solve …")
    with context.temp_override(area=area, region=region, space_data=space):
        try:
            res = bpy.ops.clip.solve_camera("INVOKE_DEFAULT")
        except Exception as e:
            print(f"[SolveWatch] ERROR: Solve operator call failed: {e}")
            return {"CANCELLED"}
    print(f"[SolveWatch] Solve-Operator returned: {res}")

    # --- 2) Read solve error ---
    avg_err: Optional[float] = None
    try:
        tracking = clip.tracking
        obj = tracking.objects.active if tracking.objects else None
        recon = obj.reconstruction if obj else None
        if recon and getattr(recon, "is_valid", False):
            avg_err = float(getattr(recon, "average_error", 0.0))
    except Exception as e:
        print(f"[SolveWatch] WARN: Could not read solve error: {e}")

    if avg_err is None:
        print("[SolveWatch] ERROR: Solve error could not be determined (invalid reconstruction).")
        return {"CANCELLED"}

    print(f"[SolveWatch] Solve OK (AvgErr={avg_err:.6f}).")
    scene["solve_error"] = float(avg_err)
    print(f"[SolveWatch] Persisted: scene['solve_error'] = {avg_err:.6f}")

    # --- 3) Threshold selection (spec: use 'resolve_error') ---
    threshold_key = "resolve_error"
    # Fallback to current solve average if the pipeline hasn't set resolve_error yet
    threshold_base = float(scene.get(threshold_key, avg_err))
    print(
        f"[SolveWatch] Cleanup threshold source: scene['{threshold_key}'] = "
        f"{threshold_base:.6f} (fallback to AvgErr if missing)."
    )

    cleanup_frames = 0  # 0 = whole sequence (interpreted by helper)
    cleanup_action = "SELECT" if bool(cleanup_mute_only) else "DELETE_TRACK"

    print(
        "[SolveWatch] Running builtin Projection-Cleanup: "
        f"key={threshold_key}, factor={cleanup_factor}, frames={cleanup_frames}, "
        f"action={cleanup_action}, dry_run={cleanup_dry_run}"
    )

    # --- 4) Builtin Cleanup in safe CLIP context ---
    try:
        with context.temp_override(area=area, region=region, space_data=space):
            report = builtin_projection_cleanup(
                context,
                error_key=threshold_key,
                factor=float(cleanup_factor),
                frames=int(cleanup_frames),
                action=cleanup_action,
                dry_run=bool(cleanup_dry_run),
            )
    except Exception as e:
        print(f"[SolveWatch] ERROR: Projection-Cleanup failed: {e}")
        return {"CANCELLED"}

    for line in report.get("log", []):
        print(line)

    affected = int(report.get("affected", 0))
    reported_thr = float(report.get("threshold", threshold_base))
    print(
        "[SolveWatch] Projection-Cleanup done: "
        f"affected={affected}, threshold={reported_thr:.6f}, "
        f"mode={report.get('action', cleanup_action)}"
    )

    # --- 5) Post-clean signal to Coordinator (affected OR coverage gaps) ---
    need_more_coverage = False
    try:
        tracking = clip.tracking
        obj = tracking.objects.active if tracking.objects else None
        recon = obj.reconstruction if obj else None
        cov = _compute_camera_coverage(clip, recon)
        need_more_coverage = bool(cov.get("has_gap", False))
        if need_more_coverage:
            print(
                "[SolveWatch] Coverage gaps detected: "
                f"first_cam={cov.get('first_cam')}, last_cam={cov.get('last_cam')}, "
                f"clip_range=[{cov.get('clip_start')}..{cov.get('clip_end')}]"
            )
    except Exception:
        # Best-effort only
        pass

    if affected > 0 or need_more_coverage:
        scene["__post_cleanup_request"] = True
        scene["__post_cleanup_threshold"] = float(reported_thr)
        print(
            "[SolveWatch] POST-CLEAN requested → Coordinator will jump to FIND_LOW "
            f"(threshold={reported_thr:.6f}, affected={affected}, coverage_gap={need_more_coverage})."
        )
    else:
        print("[SolveWatch] No POST-CLEAN request (no affected tracks and no coverage gap).")

    return {"FINISHED"}


# ---------------------------------------------------------------------------
# Convenience wrapper (for calls from __init__.py, operators, etc.)
# ---------------------------------------------------------------------------

def run_solve_watch_clean(
    context: bpy.types.Context,
    refine_limit_frames: int = 0,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Same behavior as solve_watch_clean but resolves CLIP_EDITOR override here."""
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("No CLIP_EDITOR window found (context required).")

    with context.temp_override(area=area, region=region, space_data=space):
        return solve_watch_clean(
            context,
            refine_limit_frames=int(refine_limit_frames),
            cleanup_factor=float(cleanup_factor),
            cleanup_mute_only=bool(cleanup_mute_only),
            cleanup_dry_run=bool(cleanup_dry_run),
        )

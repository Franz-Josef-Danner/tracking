# ============================
# Helper/solve_camera.py
# (solver-only cleanup; runs builtin cleanup *before* returning FINISHED)
# ============================
from __future__ import annotations

import bpy
from typing import Optional, Tuple

# side-effect import; keep
from .refine_high_error import run_refine_on_high_error  # noqa: F401
from .projection_cleanup_builtin import (
    builtin_projection_cleanup,
    find_clip_window,
)

__all__ = ("solve_watch_clean", "run_solve_watch_clean")


# -------------------------- context helpers --------------------------

def _find_clip_window(context: bpy.types.Context) -> Tuple[
    Optional[bpy.types.Area], Optional[bpy.types.Region], Optional[bpy.types.Space]
]:
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


# ----------------------------- orchestrator -----------------------------

def solve_watch_clean(
    context: bpy.types.Context,
    *,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    """Run solve, then *always* run builtin cleanup right before FINISHED.

    Notes
    -----
    - Uses scene['resolve_error'] for threshold; if missing/<=0 → fallback to
      current solve average and *persist* it to scene['resolve_error'] so the
      helper has a valid base.
    - No POST-CLEAN handshake is set (no __post_cleanup_request). Coordinator
      should not trigger its own cleanup; a tiny guard is provided below.
    """
    scn = context.scene

    # 0) Ensure CLIP_EDITOR context
    area, region, space = find_clip_window(context)
    if not area or not space or not getattr(space, "clip", None):
        print("[SolveWatch] ERROR: No active Movie Clip in CLIP_EDITOR.")
        return {"CANCELLED"}

    clip = space.clip

    # 1) Solve (synchronous)
    print("[SolveWatch] SOLVE… (EXEC_DEFAULT)")
    with context.temp_override(area=area, region=region, space_data=space):
        try:
            res = bpy.ops.clip.solve_camera("EXEC_DEFAULT")
        except Exception as e:
            print(f"[SolveWatch] ERROR: solve_camera failed: {e}")
            return {"CANCELLED"}
    print(f"[SolveWatch] solve_camera → {res}")

    # 2) Read reconstruction error
    avg_err: Optional[float] = None
    try:
        tracking = clip.tracking
        obj = tracking.objects.active if tracking.objects else None
        recon = obj.reconstruction if obj else None
        if recon and getattr(recon, "is_valid", False):
            avg_err = float(getattr(recon, "average_error", 0.0))
    except Exception as e:
        print(f"[SolveWatch] WARN: could not read average_error: {e}")

    if avg_err is None:
        print("[SolveWatch] ERROR: invalid reconstruction; aborting cleanup.")
        return {"CANCELLED"}

    scn["solve_error"] = float(avg_err)
    print(f"[SolveWatch] Solve OK (AvgErr={avg_err:.6f}) → persist scene['solve_error']")

    # 3) Establish cleanup threshold base (spec: 'resolve_error')
    thr_key = "resolve_error"
    base = float(scn.get(thr_key, 0.0))
    if base <= 0.0:
        base = float(avg_err)
        scn[thr_key] = base  # ensure helper has a non-zero base
        print(
            f"[SolveWatch] INFO: scene['{thr_key}'] missing/<=0 → fallback to AvgErr ({base:.6f})"
        )

    cleanup_frames = 0  # whole sequence
    cleanup_action = "SELECT" if bool(cleanup_mute_only) else "DELETE_TRACK"

    print(
        "[SolveWatch] Cleanup (builtin) → "
        f"error_key={thr_key}, factor={cleanup_factor}, frames={cleanup_frames}, "
        f"action={cleanup_action}, dry_run={cleanup_dry_run}"
    )

    # 4) Builtin cleanup in safe CLIP context
    try:
        with context.temp_override(area=area, region=region, space_data=space):
            report = builtin_projection_cleanup(
                context,
                error_key=thr_key,
                factor=float(cleanup_factor),
                frames=int(cleanup_frames),
                action=cleanup_action,
                dry_run=bool(cleanup_dry_run),
            )
    except Exception as e:
        print(f"[SolveWatch] ERROR: builtin cleanup failed: {e}")
        return {"CANCELLED"}

    for line in report.get("log", []):
        print(line)

    affected = int(report.get("affected", 0))
    thr_used = float(report.get("threshold", base))
    print(
        "[SolveWatch] Cleanup done → "
        f"affected={affected}, threshold={thr_used:.6f}, mode={report.get('action', cleanup_action)}"
    )

    # 5) Handshake for coordinator to SKIP its own cleanup
    scn["__solver_cleanup_done"] = True

    # 6) Return FINISHED (cleanup already executed)
    return {"FINISHED"}


def run_solve_watch_clean(
    context: bpy.types.Context,
    cleanup_factor: float = 1.0,
    cleanup_mute_only: bool = False,
    cleanup_dry_run: bool = False,
):
    area, region, space = _find_clip_window(context)
    if not area:
        raise RuntimeError("No CLIP_EDITOR window found (context required).")
    with context.temp_override(area=area, region=region, space_data=space):
        return solve_watch_clean(
            context,
            cleanup_factor=float(cleanup_factor),
            cleanup_mute_only=bool(cleanup_mute_only),
            cleanup_dry_run=bool(cleanup_dry_run),
        )


# ============================
# Operator/tracking_coordinator.py — tiny guard
# (skip Coordinator cleanup if solver already did it)
# ============================
# Inside class CLIP_OT_tracking_coordinator, in def _state_solve(self, context):
# place this immediately *after* solve_watch_clean(context) returned
# and *before* checking for POST-CLEAN or running any END-CLEANUP.

"""
scn = context.scene
if bool(scn.get("__solver_cleanup_done", False)):
    scn.pop("__solver_cleanup_done", None)
    print("[Coord] SOLVE → Solver already executed builtin cleanup → FINALIZE")
    self._state = "FINALIZE"
    return {"RUNNING_MODAL"}
"""

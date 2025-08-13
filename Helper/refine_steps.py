# Helper/refine_steps.py
import bpy
from .refine_high_error import run_refine_on_high_error


def refine_pre_resolve(context, *, threshold: float = 2.0, limit_frames: int = 0) -> int:
    """
    Refine(1) vor dem Re-Solve.
    - threshold: Pixel-Error-Schwelle für Spike-Frames (>= threshold).
    - limit_frames: 0 = alle, sonst Obergrenze der zu verarbeitenden Frames.

    Returns: Anzahl verarbeiteter Frames.
    """
    processed = run_refine_on_high_error(
        context,
        error_threshold=float(threshold),
        limit_frames=int(limit_frames),
        resolve_after=False,  # Re-Solve folgt separat explizit
    )
    return int(processed)


def refine_post_resolve(context, *, limit_frames: int = 0, resolve_after: bool = False) -> int:
    """
    Refine(2) nach dem Re-Solve.
    - nutzt scene['solve_error'] als Threshold (Auto-Mode via error_threshold=None).
    - resolve_after: optional nochmals solve_camera am Ende.

    Returns: Anzahl verarbeiteter Frames.
    """
    processed = run_refine_on_high_error(
        context,
        error_threshold=None,            # Auto: nimmt scene['solve_error']
        limit_frames=int(limit_frames),
        resolve_after=bool(resolve_after),
    )
    return int(processed)

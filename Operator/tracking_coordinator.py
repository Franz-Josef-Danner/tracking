# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Sequentieller Orchestrator **ohne Camera-Solve**

Phasen:
  FIND_LOW → JUMP → DETECT → DISTANZE → SPIKE_FILTER
  → CLEAN_SHORT_SEGMENTS → CLEAN_SHORT_TRACKS → SPLIT_CLEANUP
  → (optional) MULTI → DONE
"""
from __future__ import annotations

import time
from typing import Optional

import bpy

# --- Helper-Imports (robust) -------------------------------------------------
try:
    from ..Helper.find_low_marker_frame import run_find_low_marker_frame
    from ..Helper.jump_to_frame import run_jump_to_frame
    from ..Helper.detect import run_detect_once as _detect_once
    from ..Helper.distanze import run_distance_cleanup
    from ..Helper.spike_filter_cycle import run_marker_spike_filter_cycle
    from ..Helper.clean_short_segments import clean_short_segments
    from ..Helper.clean_short_tracks import clean_short_tracks
    from ..Helper.split_cleanup import recursive_split_cleanup
    from ..Helper.reset_state import reset_for_new_cycle
    from ..Helper.tracker_settings import apply_tracker_settings
    from ..Helper.tracking_state import reset_tracking_state
    from ..Helper.count import run_count_tracks  # optional; None-safe unten
    try:
        from ..Helper.multi import run_multi_pass
    except Exception:
        run_multi_pass = None  # type: ignore
except Exception:
    # Fallbacks für alternative Modul-Layouts
    from .find_low_marker_frame import run_find_low_marker_frame  # type: ignore
    from .jump_to_frame import run_jump_to_frame  # type: ignore
    from .detect import run_detect_once as _detect_once  # type: ignore
    from .distanze import run_distance_cleanup  # type: ignore
    from .spike_filter_cycle import run_marker_spike_filter_cycle  # type: ignore
    from .clean_short_segments import clean_short_segments  # type: ignore
    from .clean_short_tracks import clean_short_tracks  # type: ignore
    from .split_cleanup import recursive_split_cleanup  # type: ignore
    from .reset_state import reset_for_new_cycle  # type: ignore
    from .tracker_settings import apply_tracker_settings  # type: ignore
    from .tracking_state import reset_tracking_state  # type: ignore
    try:
        from .count import run_count_tracks  # type: ignore
    except Exception:
        run_count_tracks = None  # type: ignore
    try:
        from .multi import run_multi_pass  # type: ignore
    except Exception:
        run_multi_pass = None  # type: ignore
__all__ = ("CLIP_OT_tracking_coordinator",)

# --- Utilities ---------------------------------------------------------------
def _log(msg: str) -> None:
    print(f"[COORD] {msg}")


def _safe_count(context: bpy.types.Context) -> Optional[int]:
    try:
        if run_count_tracks is None:
            return None
        return int(run_count_tracks(context))
    except Exception:
        return None


# --- Orchestrierung ----------------------------------------------------------
def _orchestrate_once(context: bpy.types.Context) -> None:
    """Tracking-&-Cleanup Sequenz ohne Solve."""
    clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
    if clip is None:
        raise RuntimeError("Kein aktiver Clip im CLIP_EDITOR.")

    reset_for_new_cycle(context)
    reset_tracking_state(context)

    # 1) FIND_LOW – robust gegen Dict/None
    t0 = time.time()
    low = run_find_low_marker_frame(context)
    _log(f"FindLow: result={low} dt={time.time()-t0:.3f}s")
    if isinstance(low, dict):
        st = str(low.get("status", "")).upper()
        if st == "FOUND":
            target_frame = int(low.get("frame"))
        elif st == "NONE":
            return  # nichts zu tun
        else:
            raise RuntimeError(f"FindLow failed: {low!r}")
    else:
        if low is None:
            return
        target_frame = int(low)
    # 2) JUMP – Keyword-Call; kein Legacy-Positionsarg
    try:
        run_jump_to_frame(context, frame=int(target_frame))
    except TypeError:
        # Legacy-Helfer ohne frame-Param: Frame direkt setzen, dann Helper aufrufen
        try:
            (getattr(context, "scene", None) or bpy.context.scene).frame_set(int(target_frame))
        except Exception:
            pass
        try:
            run_jump_to_frame(context)
        except Exception:
            pass

    # 3) Tracker-Settings harmonisieren
    apply_tracker_settings(context)

    # 4) DETECT – am Ziel-Frame; korrekte Kwargs; kein „default_min“-Kram
    _detect_once(
        context,
        start_frame=int(target_frame),
        threshold=None,   # SSOT: Helper/Scene-Keys
        select=True
    )

    # 5) DISTANZE – Pflichtarg frame setzen; min_distance automatisch
    run_distance_cleanup(
        context,
        frame=int(target_frame),
        min_distance=None,                # Auto (kc_detect_min_distance_px → … → Fallback)
        require_selected_new=True,
        include_muted_old=False,
        select_remaining_new=True,
        verbose=True
    )

    # 6) SPIKE FILTER (tolerant)
    try:
        run_marker_spike_filter_cycle(context)
    except Exception:
        pass

    # 7) CLEAN SHORTS
    try:
        clean_short_segments(context)
    except Exception:
        pass
    try:
        clean_short_tracks(context)
    except Exception:
        pass

    # 8) SPLIT CLEANUP
    try:
        recursive_split_cleanup(context)
    except Exception:
        pass

    # 9) Optional MULTI
    try:
        if run_multi_pass is not None:
            run_multi_pass(context, repeat_count=6)
    except Exception:
        pass

    # 10) Telemetrie
    cnt = _safe_count(context)
    if cnt is not None:
        _log(f"Post-Cleanup Marker Count: {cnt}")

# --- Operator ----------------------------------------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator (No Solve)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Tracking Coordinator (No Solve)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        try:
            _orchestrate_once(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Coordinator failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Tracking & Cleanup abgeschlossen (ohne Solve).")
        return {'FINISHED'}


# Optional: lokale Registrierung (falls nicht über Operator/__init__.py)
def register():
    try:
        bpy.utils.register_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)
    except Exception:
        pass

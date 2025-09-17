# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Sequentieller Orchestrator **ohne Camera-Solve**

Phasen (final):
  FIND_LOW → JUMP → DETECT → DISTANZE → SPIKE_FILTER → CLEAN_SHORT_SEGMENTS
  → CLEAN_SHORT_TRACKS → SPLIT_CLEANUP → (optional) MULTI → DONE

Kein Solve, kein Eval/Refine, keine Post-Solve-Policies. Der Operator endet
nach Tracking & Cleanup mit {'FINISHED'}.
"""
from __future__ import annotations

import time
from typing import Optional

import bpy

# ----------------------------- robuste Helper-Imports -------------------------
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

# Wichtig: KEINE Solve-Imports, KEINE Solve-Helper, KEINE Solve-Hooks.

__all__ = ("CLIP_OT_tracking_coordinator",)


# --------------------------------- Utilities ----------------------------------
def _log(msg: str) -> None:
    # bewusst minimal – keine laute Konsole
    print(f"[COORD] {msg}")


def _safe_count(context: bpy.types.Context) -> Optional[int]:
    """Ermittelt optional die Markeranzahl; None-tolerant, wenn count fehlt."""
    try:
        if run_count_tracks is None:
            return None
        return int(run_count_tracks(context))
    except Exception:
        return None


# -------------------------------- Orchestrierung ------------------------------
def _orchestrate_once(context: bpy.types.Context) -> None:
    """Eine vollständige Tracking-&-Cleanup-Sequenz ohne Solve."""
    clip = getattr(context, "edit_movieclip", None)
    if clip is None:
        clip = getattr(context.space_data, "clip", None)
    if clip is None:
        raise RuntimeError("Kein aktiver Clip im CLIP_EDITOR.")

    reset_for_new_cycle(context)
    reset_tracking_state(context)

    # 1) FIND_LOW
    t0 = time.time()
    target_frame = run_find_low_marker_frame(context)
    _log(f"FindLow: frame={target_frame} dt={time.time()-t0:.3f}s")
    if target_frame is None:
        # Nichts zu tun
        return

    # 2) JUMP
    run_jump_to_frame(context, int(target_frame))

    # 3) Tracker-Settings harmonisieren
    apply_tracker_settings(context)

    # 4) DETECT (einmal, kontrolliert)
    _detect_once(context, detect_threshold=None)

    # 5) DISTANZE
    run_distance_cleanup(context)

    # 6) SPIKE_FILTER (projektion-agnostisch; rein markerbasiert)
    try:
        run_marker_spike_filter_cycle(context)
    except Exception:
        pass  # tolerant – nicht kritisch

    # 7) CLEAN_SHORT_SEGMENTS / CLEAN_SHORT_TRACKS
    try:
        clean_short_segments(context)
    except Exception:
        pass
    try:
        clean_short_tracks(context)
    except Exception:
        pass

    # 8) SPLIT_CLEANUP (rekursiv)
    try:
        recursive_split_cleanup(context)
    except Exception:
        pass

    # 9) Optional MULTI-Pass (wenn vorhanden), nur wenn noch Budget/Bedarf
    try:
        if run_multi_pass is not None:
            run_multi_pass(context, repeat_count=6)
    except Exception:
        pass

    # 10) Optional: Status zählen (kein Gate, reine Telemetrie)
    cnt = _safe_count(context)
    if cnt is not None:
        _log(f"Post-Cleanup Marker Count: {cnt}")


# ------------------------------ Operator-Definition ---------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Koordiniert Tracking & Cleanup (ohne Camera-Solve)."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Tracking Coordinator (No Solve)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context):
        try:
            _orchestrate_once(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Coordinator failed: {exc}")
            return {'CANCELLED'}

        # Keine Solve-Schleifen, keine weiteren Resets → direkt fertig.
        self.report({'INFO'}, "Tracking & Cleanup abgeschlossen (ohne Solve).")
        return {'FINISHED'}

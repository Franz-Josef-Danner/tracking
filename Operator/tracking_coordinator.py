# SPDX-License-Identifier: GPL-2.0-or-later
# tracking_coordinator.py — Reset: ausschließlich Bootstrap behalten

from __future__ import annotations
import bpy

# Placeholder-Konstanten (müssen aus deinem Projekt kommen)
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0


def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)

    # interne States (hier als lokale Variablen statt self)
    state = "INIT"
    detect_attempts = 0
    jump_done = False
    repeat_map = {}
    bidi_started = False

    # Cycle reset
    cycle_active = False
    cycle_target_frame = None
    cycle_iterations = 0  # reset counter

    # Spike reset
    spike_threshold = float(
        getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START)
        or _DEFAULT_SPIKE_START
    )
    spike_floor = 10.0
    spike_floor_hit = False

    # Solve/Eval/Refine
    pending_eval_after_solve = False
    did_refine_this_cycle = False

    # --- NEU: Solve-Error-Merker zurücksetzen ---
    last_solve_error = None
    same_error_repeat_count = 0

    # Rückgabe oder Logging, falls gewünscht
    return {
        "state": state,
        "detect_attempts": detect_attempts,
        "jump_done": jump_done,
        "repeat_map": repeat_map,
        "bidi_started": bidi_started,
        "cycle_active": cycle_active,
        "cycle_target_frame": cycle_target_frame,
        "cycle_iterations": cycle_iterations,
        "spike_threshold": spike_threshold,
        "spike_floor": spike_floor,
        "spike_floor_hit": spike_floor_hit,
        "pending_eval_after_solve": pending_eval_after_solve,
        "did_refine_this_cycle": did_refine_this_cycle,
        "last_solve_error": last_solve_error,
        "same_error_repeat_count": same_error_repeat_count,
    }

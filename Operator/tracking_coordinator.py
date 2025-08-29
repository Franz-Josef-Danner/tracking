# SPDX-License-Identifier: GPL-2.0-or-later
# tracking_coordinator.py — Reset: ausschließlich Bootstrap behalten


from __future__ import annotations
import bpy




def bootstrap(context: bpy.types.Context) -> None:
scn = context.scene
scn[_LOCK_KEY] = False
scn[_BIDI_ACTIVE_KEY] = False
scn[_BIDI_RESULT_KEY] = ""
scn.pop(_GOTO_KEY, None)

self._state = "INIT"
self._detect_attempts = 0
self._jump_done = False
self._repeat_map = {}
self._bidi_started = False

        # Cycle reset
self._cycle_active = False
self._cycle_target_frame = None
self._cycle_iterations = 0  # reset counter

        # Spike reset
self._spike_threshold = float(getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START)
self._spike_floor = 10.0
self._spike_floor_hit = False

        # Solve/Eval/Refine
self._pending_eval_after_solve = False
self._did_refine_this_cycle = False

        # --- NEU: Solve-Error-Merker zurücksetzen ---
self._last_solve_error = None
self._same_error_repeat_count = 0
pass

# SPDX-License-Identifier: GPL-2.0-or-later
"""
tracking_coordinator.py – Minimaler Coordinator mit Bootstrap-Reset
- Stellt den Operator `CLIP_OT_tracking_coordinator` bereit (Button-Target).
- Führt beim Ausführen ein definierte(r) Bootstrap/Reset im Scene-State aus.
"""

from __future__ import annotations
import bpy
from ..Helper.tracker_settings import apply_tracker_settings
from ..Helper.marker_helper_main import marker_helper_main
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once
from ..Helper.distanze import run_distance_cleanup

# --- Keys / Defaults (an Projekt-Konstanten anpassen, falls vorhanden) -----
_LOCK_KEY = "tco_lock"
_BIDI_ACTIVE_KEY = "tco_bidi_active"
_BIDI_RESULT_KEY = "tco_bidi_result"
_GOTO_KEY = "tco_goto"
_DEFAULT_SPIKE_START = 50.0
_CYCLE_LOCK_KEY = "tco_cycle_lock"
# Erste, klar definierte Phase des modularen Zyklus
_CYCLE_PHASES = (
    "DETECT",
    "DISTANZE",
)
__all__ = ("CLIP_OT_tracking_coordinator", "bootstrap")


# --- Bootstrap: setzt Scene-Flags und interne Reset-Variablen --------------

def _resolve_clip(context: bpy.types.Context):
    """Robuster Clip-Resolver (Edit-Clip, Space-Clip, erster Clip)."""
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    return clip


def _snapshot_track_ptrs(context: bpy.types.Context) -> list[int]:
    """
    Snapshot der aktuellen Track-Pointer.
    WICHTIG: Diese Werte NICHT in Scene/IDProperties persistieren (32-bit Limit)!
    Nur ephemer im Python-Kontext verwenden.
    """
    clip = _resolve_clip(context)
    if not clip:
        return []
    try:
        return [int(t.as_pointer()) for t in clip.tracking.tracks]
    except Exception:
        return []


def _get_state(scn: bpy.types.Scene) -> dict:
    """Kurzhelper für den persistierten State-Container."""
    return scn.get("tco_state", {})


def _cycle_begin(context: bpy.types.Context, *, target_frame: int | None) -> dict:
    """
    Startet einen modularen, synchron abgearbeiteten Zyklus.
    Reentrancy wird über _CYCLE_LOCK_KEY verhindert.
    """
    scn = context.scene
    if scn.get(_CYCLE_LOCK_KEY, False):
        # Bereits aktiv – nicht erneut starten
        return {"status": "SKIPPED", "reason": "cycle_locked"}

    scn[_CYCLE_LOCK_KEY] = True
    try:
        st = _get_state(scn)
        st["cycle_active"] = True
        st["cycle_iterations"] = int(st.get("cycle_iterations", 0)) + 1
        st["cycle_target_frame"] = int(target_frame) if target_frame is not None else int(scn.frame_current)
        st["cycle_phase_index"] = 0
        st["cycle_last_result"] = None
        st["cycle_results"] = []
        scn["tco_state"] = st  # zurückschreiben

        # Ephemerer Kontext für 64-bit Pointer & kompakte Rückgabe
        cycle_ctx = {
            "pre_ptrs": set(_snapshot_track_ptrs(context)),  # 64-bit Pointer nur hier halten
            "results": {},
        }

        # SYNCHRONE Abarbeitung ALLER Phasen (keine Modal-Nebenläufigkeit)
        last: dict | None = None
        while True:
            step_res = _cycle_step(context, cycle_ctx)
            last = step_res
            # Ende, wenn DONE/NOOP oder keine aktive Phase mehr
            st = _get_state(scn)
            if step_res.get("status") in {"DONE", "NOOP"}:
                break
            if (not st.get("cycle_active")) or int(st.get("cycle_phase_index", 0)) >= len(_CYCLE_PHASES):
                break
        # Kompakte, UI-taugliche Rückgabe der Phasenresultate
        out = dict(cycle_ctx.get("results", {}))
        out["status"] = "DONE"
        return out
    finally:
        # Lock unmittelbar wieder lösen; jede Phase läuft synchron im Operator-Kontext,
        # dadurch keine konkurrierenden modal-Handler nötig.
        scn[_CYCLE_LOCK_KEY] = False


def _cycle_step(context: bpy.types.Context, cycle_ctx: dict) -> dict:
    """Führt genau eine Phase basierend auf cycle_phase_index aus."""
    scn = context.scene
    st = _get_state(scn)
    idx = int(st.get("cycle_phase_index", 0))

    if not st.get("cycle_active", False):
        return {"status": "NOOP", "reason": "cycle_not_active"}

    if idx >= len(_CYCLE_PHASES):
        # Zyklus fertig
        st["cycle_active"] = False
        scn["tco_state"] = st
        return {"status": "DONE"}

    phase = _CYCLE_PHASES[idx]
    if phase == "DETECT":
        # Phase 1: Marker-Detection am Ziel-Frame (modular, separater Helper)
        res = run_detect_once(context, start_frame=st.get("cycle_target_frame"))
        # Ergebnisbookkeeping
        results = list(st.get("cycle_results", []))
        results.append({"phase": "DETECT", "result": dict(res) if hasattr(res, "items") else res})
        st["cycle_results"] = results
        st["cycle_phase_index"] = idx + 1
        scn["tco_state"] = st
        return {"status": "OK", "phase": phase, "result": res}

    if phase == "DISTANZE":
        # Phase 2: Distanz-Cleanup für NEUE Marker relativ zu Pre-Snapshot
        pre_ptrs = set(cycle_ctx.get("pre_ptrs") or [])
        frame = int(st.get("cycle_target_frame"))
        try:
            # Defaults aus Helper: close_dist_rel=0.01, reselect_only_remaining=True, select_remaining_new=True
            res = run_distance_cleanup(context, pre_ptrs=pre_ptrs, frame=frame)
        except Exception as e:
            res = {"status": "FAILED", "reason": str(e)}
        st["cycle_last_result"] = res
        # Ergebnisbookkeeping
        results = list(st.get("cycle_results", []))
        results.append({"phase": "DISTANZE", "result": dict(res) if hasattr(res, "items") else res})
        st["cycle_results"] = results
        st["cycle_phase_index"] = idx + 1
        # Zyklus nach letzter Phase schließen
        if st["cycle_phase_index"] >= len(_CYCLE_PHASES):
            st["cycle_active"] = False
        scn["tco_state"] = st
        # Für unmittelbare Rückgabe zusätzlich im ephemeren Kontext ablegen
        cycle_ctx["results"]["DISTANZE"] = res if isinstance(res, dict) else {"status": str(res)}
        return {"status": "OK", "phase": phase, "result": res}

    # Unbekannte Phase (zukunftssicherer Fallback)
    st["cycle_phase_index"] = idx + 1
    scn["tco_state"] = st
    return {"status": "OK", "phase": phase, "result": None}

def bootstrap(context: bpy.types.Context) -> None:
    scn = context.scene
    # --- Zuerst Tracker-Settings setzen ---
    try:
        res = apply_tracker_settings(context, scene=scn, log=True)
        # Optional: kurzes Feedback im Scene-State persistieren
        scn["tco_last_tracker_settings"] = dict(res)
    except Exception as exc:
        scn["tco_last_tracker_settings"] = {"status": "FAILED", "reason": str(exc)}

    # --- Danach Marker-Helper starten ---
    try:
        ok, count, info = marker_helper_main(context)
        scn["tco_last_marker_helper"] = {
            "ok": bool(ok),
            "count": int(count),
            "info": dict(info) if hasattr(info, "items") else info,
        }
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}

    # Globale Scene-Flags
    scn[_LOCK_KEY] = False
    scn[_BIDI_ACTIVE_KEY] = False
    scn[_BIDI_RESULT_KEY] = ""
    scn.pop(_GOTO_KEY, None)

    # Interne State-Container (falls später in Scene benötigt, hier persistieren)
    scn["tco_state"] = {
        "state": "INIT",
        "detect_attempts": 0,
        "jump_done": False,
        "repeat_map": {},          # serialisierbar halten
        "bidi_started": False,

        # Cycle
        "cycle_active": False,
        "cycle_target_frame": None,
        "cycle_iterations": 0,

        # Spike
        "spike_threshold": float(
            getattr(scn, "spike_start_threshold", _DEFAULT_SPIKE_START) or _DEFAULT_SPIKE_START
        ),
        "spike_floor": 10.0,
        "spike_floor_hit": False,

        # Solve/Eval/Refine
        "pending_eval_after_solve": False,
        "did_refine_this_cycle": False,

        # Solve-Error-Merker
        "last_solve_error": None,
        "same_error_repeat_count": 0,
    }


# --- Operator: wird vom UI-Button aufgerufen -------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator Bootstrap"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator starten"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Optional enger machen: nur im Clip Editor erlauben
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        try:
            bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator bootstrap reset complete.")

        # --- Direkt im Anschluss Low-Marker-Frame suchen ---
        try:
            res_low = run_find_low_marker_frame(context)
            if res_low.get("status") == "FOUND":
                frame = res_low.get("frame")
                self.report({'INFO'}, f"Low-marker frame gefunden: {frame}")
                # --- Playhead auf Frame setzen ---
                res_jump = run_jump_to_frame(context, frame=frame, repeat_map={})
                if res_jump.get("status") == "OK":
                    self.report({'INFO'}, f"Playhead gesetzt auf Frame {res_jump.get('frame')}")
                    # --- Direkt danach: modularen Zyklus starten (Phase 1 = DETECT) ---
                    try:
                        cyc = _cycle_begin(context, target_frame=res_jump.get("frame"))
                        if cyc.get("status") in {"OK", "DONE", "DONE"}:
                            # KPI direkt aus der Rückgabe (ephemer, pointer-sicher)
                            det_res = cyc.get("DETECT", {}) or {}
                            dis_res = cyc.get("DISTANZE", {}) or {}
                            self.report({'INFO'}, (
                                f"Cycle fertig: "
                                f"DETECT={det_res.get('status','n/a')} new={det_res.get('new_tracks', 0)}; "
                                f"DISTANZE={dis_res.get('status','n/a')} removed={dis_res.get('removed', 0)}"
                            ))
                        else:
                            self.report({'WARNING'}, f"Cycle wurde übersprungen: {cyc}")
                    except Exception as cyc_exc:
                        self.report({'ERROR'}, f"Cycle-Start fehlgeschlagen: {cyc_exc}")
                else:
                    self.report({'WARNING'}, f"Jump failed: {res_jump}")
            else:
                self.report({'INFO'}, f"Kein Low-marker frame gefunden: {res_low}")
        except Exception as exc:
            self.report({'ERROR'}, f"Helper call failed: {exc}")

        return {'FINISHED'}


# --- Registrierung ----------------------------------------------------------
def register():
    bpy.utils.register_class(CLIP_OT_tracking_coordinator)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_tracking_coordinator)


# Optional: lokale Tests beim Direktlauf
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

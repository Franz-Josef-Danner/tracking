"""
tracking_coordinator.py – Streng sequentieller, MODALER Orchestrator
- Phasen: FIND_LOW → JUMP → DETECT → DISTANZE (hart getrennt, seriell)
- Jede Phase startet erst, wenn die vorherige abgeschlossen wurde.
"""

from __future__ import annotations
import bpy
from ..Helper.find_low_marker_frame import run_find_low_marker_frame
from ..Helper.jump_to_frame import run_jump_to_frame
from ..Helper.detect import run_detect_once
from ..Helper.distanze import run_distance_cleanup
# Nach dem Distanz-Cleanup soll die Marker-Anzahl bewertet werden.
# Die Evaluierungsfunktion wird separat importiert.
try:
    # Versuche, die Zählfunktion aus Helper.count zu importieren.
    from ..Helper.count import evaluate_marker_count  # type: ignore
except Exception:
    # Fallback für Umgebungen, in denen Helper.count möglicherweise ein direktes
    # Modul ohne Paketstruktur ist.  In diesem Fall wird evaluiert, indem
    # count.py im aktuellen Verzeichnis importiert wird.
    try:
        from .count import evaluate_marker_count  # type: ignore
    except Exception:
        # Wenn die Importversuche fehlschlagen, ist evaluate_marker_count nicht vorhanden.
        evaluate_marker_count = None  # type: ignore
from ..Helper.tracker_settings import apply_tracker_settings
from ..Helper.marker_helper_main import marker_helper_main

__all__ = ("CLIP_OT_tracking_coordinator",)

# --- Orchestrator-Phasen ----------------------------------------------------
PH_FIND_LOW   = "FIND_LOW"
PH_JUMP       = "JUMP"
PH_DETECT     = "DETECT"
PH_DISTANZE   = "DISTANZE"

# ---- intern: State Keys / Locks -------------------------------------------
_LOCK_KEY = "tco_lock"

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

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

def _bootstrap(context: bpy.types.Context) -> None:
    """Minimaler Reset + sinnvolle Defaults; Helper initialisieren."""
    scn = context.scene
    # Tracker-Settings
    try:
        scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=True))
    except Exception as exc:
        scn["tco_last_tracker_settings"] = {"status": "FAILED", "reason": str(exc)}
    # Marker-Helper
    try:
        ok, count, info = marker_helper_main(context)
        scn["tco_last_marker_helper"] = {"ok": bool(ok), "count": int(count), "info": dict(info) if hasattr(info, "items") else info}
    except Exception as exc:
        scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}
    scn[_LOCK_KEY] = False


# --- Operator: wird vom UI-Button aufgerufen -------------------------------
class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Kaiserlich: Tracking Coordinator (Modal, strikt sequenziell)"""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Kaiserlich: Coordinator (Modal)"
    # Hinweis: Blender kennt nur GRAB_CURSOR / GRAB_CURSOR_X / GRAB_CURSOR_Y.
    # GRAB_CURSOR_XY existiert nicht → Validation-Error beim Register.
    # Modalität kommt über modal(); Cursor-Grabbing ist nicht nötig.
    bl_options = {"REGISTER", "UNDO"}

    # — Laufzeit-State (nur Operator, nicht Szene) —
    _timer: object | None = None
    phase: str = PH_FIND_LOW
    target_frame: int | None = None
    repeat_map: dict[int, int] = {}
    pre_ptrs: set[int] | None = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context is not None and context.scene is not None

    def execute(self, context: bpy.types.Context):
        # Bootstrap/Reset
        try:
            _bootstrap(context)
        except Exception as exc:
            self.report({'ERROR'}, f"Bootstrap failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Coordinator: Bootstrap OK")

        # Modal starten
        self.phase = PH_FIND_LOW
        self.target_frame = None
        self.repeat_map = {}
        self.pre_ptrs = None

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context, *, info: str | None = None, cancelled: bool = False):
        # Timer sauber entfernen
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        if info:
            self.report({'INFO'} if not cancelled else {'WARNING'}, info)
        return {'CANCELLED' if cancelled else 'FINISHED'}

    def modal(self, context: bpy.types.Context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # PHASE 1: FIND_LOW
        if self.phase == PH_FIND_LOW:
            res = run_find_low_marker_frame(context)
            st = res.get("status")
            if st == "FAILED":
                return self._finish(context, info=f"FIND_LOW FAILED → {res.get('reason')}", cancelled=True)
            if st == "NONE":
                return self._finish(context, info="Kein Low-Marker-Frame gefunden – Sequenz endet.", cancelled=False)
            self.target_frame = int(res.get("frame"))
            self.report({'INFO'}, f"Low-Marker-Frame: {self.target_frame}")
            self.phase = PH_JUMP
            return {'RUNNING_MODAL'}

        # PHASE 2: JUMP
        if self.phase == PH_JUMP:
            if self.target_frame is None:
                return self._finish(context, info="JUMP: Kein Ziel-Frame gesetzt.", cancelled=True)
            rj = run_jump_to_frame(context, frame=self.target_frame, repeat_map=self.repeat_map)
            if rj.get("status") != "OK":
                return self._finish(context, info=f"JUMP FAILED → {rj}", cancelled=True)
            self.report({'INFO'}, f"Playhead gesetzt: f{rj.get('frame')} (repeat={rj.get('repeat_count')})")
            # **WICHTIG**: Pre-Snapshot direkt vor DETECT
            self.pre_ptrs = set(_snapshot_track_ptrs(context))
            self.phase = PH_DETECT
            return {'RUNNING_MODAL'}

        # PHASE 3: DETECT
        if self.phase == PH_DETECT:
            rd = run_detect_once(context, start_frame=self.target_frame)
            if rd.get("status") != "READY":
                return self._finish(context, info=f"DETECT FAILED → {rd}", cancelled=True)
            new_cnt = int(rd.get("new_tracks", 0))
            self.report({'INFO'}, f"DETECT @f{self.target_frame}: new={new_cnt}")
            self.phase = PH_DISTANZE
            return {'RUNNING_MODAL'}

        # PHASE 4: DISTANZE
        if self.phase == PH_DISTANZE:
            if self.pre_ptrs is None or self.target_frame is None:
                return self._finish(context, info="DISTANZE: Pre-Snapshot oder Ziel-Frame fehlt.", cancelled=True)
            try:
                dis = run_distance_cleanup(
                    context,
                    pre_ptrs=self.pre_ptrs,
                    frame=int(self.target_frame),
                    distance_unit="pixel",
                    min_distance=200.0,              # dein Härtetest
                    require_selected_new=True,       # exakt wie gefordert
                    include_muted_old=False,         # nur nicht gemutete alte Marker
                    select_remaining_new=True,
                    verbose=True,
                )
            except Exception as exc:
                return self._finish(context, info=f"DISTANZE FAILED → {exc}", cancelled=True)
            # Nach dem Distanz-Cleanup Marker-Anzahl evaluieren, falls verfügbar.
            removed = dis.get('removed', 0)
            kept = dis.get('kept', 0)
            # Aktuelle Track-Pointer nach dem Cleanup ermitteln
            try:
                current_ptrs = set(_snapshot_track_ptrs(context))
            except Exception:
                current_ptrs = set()
            # Neue Pointer sind die, die noch existieren, aber vor DETECT nicht vorhanden waren
            new_ptrs_after_cleanup = set()
            if isinstance(self.pre_ptrs, set) and current_ptrs:
                new_ptrs_after_cleanup = current_ptrs.difference(self.pre_ptrs)
            # Default-Grenzwerte festlegen; falls die Szene eigene Werte definiert,
            # diese verwenden.  Andernfalls breite Grenzen nutzen.
            scn = context.scene
            try:
                min_marker = int(scn.get('tco_min_marker', 0))
                max_marker = int(scn.get('tco_max_marker', 10**9))
            except Exception:
                min_marker = 0
                max_marker = 10**9
            # Marker-Anzahl auswerten, sofern die Funktion importiert werden konnte
            if evaluate_marker_count is not None:
                try:
                    eval_res = evaluate_marker_count(
                        new_ptrs_after_cleanup=new_ptrs_after_cleanup,
                        min_marker=min_marker,
                        max_marker=max_marker,
                    )
                except Exception as exc:
                    eval_res = {"status": "ERROR", "reason": str(exc), "count": len(new_ptrs_after_cleanup)}
                # Ergebnis im Szenen-Status ablegen und loggen
                scn["tco_last_marker_count"] = eval_res
                self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}")
            else:
                # Wenn keine Zählfunktion verfügbar ist, nur das Cleanup melden
                self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}")
            return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)

        # Fallback (unbekannte Phase)
        return self._finish(context, info=f"Unbekannte Phase: {self.phase}", cancelled=True)


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

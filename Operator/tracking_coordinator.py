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
# Versuche, die Auswertungsfunktion für die Markeranzahl zu importieren.
# Diese Funktion soll nach dem Distanz-Cleanup ausgeführt werden und
# verwendet interne Grenzwerte aus der count.py. Es werden keine
# zusätzlichen Parameter übergeben.
try:
    from ..Helper.count import evaluate_marker_count  # type: ignore
except Exception:
    try:
        from .count import evaluate_marker_count  # type: ignore
    except Exception:
        evaluate_marker_count = None  # type: ignore
from ..Helper.tracker_settings import apply_tracker_settings
from ..Helper.marker_helper_main import marker_helper_main
# Import the detect threshold key so we can reference the last used value
try:
    # Local import when running inside the package structure
    from ..Helper.detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
except Exception:
    try:
        # Fallback when module layout differs
        from .detect import DETECT_LAST_THRESHOLD_KEY  # type: ignore
    except Exception:
        # Default value if import fails
        DETECT_LAST_THRESHOLD_KEY = "last_detection_threshold"  # type: ignore

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
    # Aktueller Detection-Threshold; wird nach jedem Detect-Aufruf aktualisiert.
    detection_threshold: float | None = None

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
        # Threshold-Zurücksetzen: beim ersten Detect-Aufruf wird der Standardwert verwendet
        self.detection_threshold = None

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
            # Beim ersten Detect-Aufruf wird kein Threshold übergeben (None → Standardwert)
            _kwargs: dict[str, object] = {"start_frame": self.target_frame}
            # Wenn bereits ein Threshold aus vorherigen Iterationen vorliegt, diesen mitgeben
            if self.detection_threshold is not None:
                _kwargs["threshold"] = float(self.detection_threshold)
            rd = run_detect_once(context, **_kwargs)
            if rd.get("status") != "READY":
                return self._finish(context, info=f"DETECT FAILED → {rd}", cancelled=True)
            new_cnt = int(rd.get("new_tracks", 0))
            # Merke den verwendeten Threshold für spätere Anpassungen
            try:
                self.detection_threshold = float(rd.get("threshold", self.detection_threshold))
            except Exception:
                pass
            self.report({'INFO'}, f"DETECT @f{self.target_frame}: new={new_cnt}, thr={self.detection_threshold}")
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

            removed = dis.get('removed', 0)
            kept = dis.get('kept', 0)

            # NUR neue Tracks berücksichtigen, die AM target_frame einen Marker besitzen
            new_ptrs_after_cleanup: set[int] = set()
            clip = _resolve_clip(context)
            if clip and isinstance(self.pre_ptrs, set):
                trk = getattr(clip, "tracking", None)
                if trk and hasattr(trk, "tracks"):
                    for t in trk.tracks:
                        ptr = int(t.as_pointer())
                        if ptr in self.pre_ptrs:
                            continue  # nicht neu
                        try:
                            m = t.markers.find_frame(int(self.target_frame), exact=True)
                        except TypeError:
                            # ältere Blender-Builds ohne exact-Param
                            m = t.markers.find_frame(int(self.target_frame))
                        if m:
                            new_ptrs_after_cleanup.add(ptr)

            # Markeranzahl auswerten, sofern die Zählfunktion vorhanden ist.
            eval_res = None
            scn = context.scene
            if evaluate_marker_count is not None:
                try:
                    # Aufruf ohne explizite Grenzwerte – count.py kennt diese selbst.
                    eval_res = evaluate_marker_count(new_ptrs_after_cleanup=new_ptrs_after_cleanup)  # type: ignore
                except Exception as exc:
                    # Wenn der Aufruf fehlschlägt, Fehlermeldung zurückgeben.
                    eval_res = {"status": "ERROR", "reason": str(exc), "count": len(new_ptrs_after_cleanup)}
                # Ergebnis im Szenen-Status speichern
                try:
                    scn["tco_last_marker_count"] = eval_res
                except Exception:
                    pass

                # Prüfe, ob Markeranzahl außerhalb des gültigen Bandes liegt
                status = str(eval_res.get("status", "")) if isinstance(eval_res, dict) else ""
                if status in {"TOO_FEW", "TOO_MANY"}:
                    # *** Distanzé-Semantik: nur den MARKER am aktuellen Frame löschen ***
                    deleted_markers = 0
                    if clip and new_ptrs_after_cleanup:
                        trk = getattr(clip, "tracking", None)
                        if trk and hasattr(trk, "tracks"):
                            curf = int(self.target_frame)
                            for t in trk.tracks:
                                if int(t.as_pointer()) in new_ptrs_after_cleanup:
                                    # robust: solange Marker @frame existiert, löschen
                                    while True:
                                        try:
                                            _m = None
                                            try:
                                                _m = t.markers.find_frame(curf, exact=True)
                                            except TypeError:
                                                _m = t.markers.find_frame(curf)
                                            if not _m:
                                                break
                                            t.markers.delete_frame(curf)
                                            deleted_markers += 1
                                        except Exception:
                                            break
                            # Flush/Refresh, damit der Effekt sofort greift
                            try:
                                bpy.context.view_layer.update()
                                scn.frame_set(curf)
                            except Exception:
                                pass

                    # Threshold neu berechnen:
                    # threshold = max(detection_threshold * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                    try:
                        anzahl_neu = float(eval_res.get("count", 0))
                        marker_min = float(eval_res.get("min", 0))
                        marker_max = float(eval_res.get("max", 0))
                        # bevorzugt aus Szene (falls gesetzt), sonst Mittelwert
                        marker_adapt = float(scn.get("marker_adapt", 0.0)) or ((marker_min + marker_max) / 2.0)
                        if marker_adapt <= 0.0:
                            marker_adapt = 1.0
                        base_thr = float(self.detection_threshold if self.detection_threshold is not None
                                         else scn.get(DETECT_LAST_THRESHOLD_KEY, 0.75))
                        self.detection_threshold = max(base_thr * ((anzahl_neu + 0.1) / marker_adapt), 0.0001)
                    except Exception:
                        pass

                    self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}, deleted_markers={deleted_markers}, thr→{self.detection_threshold}")
                    # Zurück zu DETECT mit neuem Threshold
                    self.phase = PH_DETECT
                    return {'RUNNING_MODAL'}

                # ENOUGH → normal beenden
                self.report({'INFO'}, f"DISTANZE @f{self.target_frame}: removed={removed} kept={kept}, eval={eval_res}")
                return self._finish(context, info="Sequenz abgeschlossen.", cancelled=False)

            # Wenn keine Auswertungsfunktion vorhanden ist, einfach abschließen
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

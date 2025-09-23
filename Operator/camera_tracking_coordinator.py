import bpy
from bpy.types import Operator
import math

# Optionaler Direktimport für Fallback (Bootstrap)
try:
    from .bootstrap_O import CLIP_OT_bootstrap_cycle  # type: ignore
except Exception:
    CLIP_OT_bootstrap_cycle = None  # type: ignore

# Optional: Bidirectional-Track aus Helper registrieren/nutzen
try:
    from ..Helper.bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
except Exception:
    try:
        from .bidirectional_track import CLIP_OT_bidirectional_track  # type: ignore
    except Exception:
        CLIP_OT_bidirectional_track = None  # type: ignore

# Optional: Reset (für Neustarts)
try:
    from ..Helper.reset_state import reset_for_new_cycle  # type: ignore
except Exception:
    reset_for_new_cycle = None  # type: ignore

# NEU: Orchestrator-Ablauf (STRM → Init → Autotune/Seeding → Online → Models → Cleanup → KPI/Preset)
try:
    from ..Helper.orchestrator import run_full_cycle  # type: ignore
except Exception:
    run_full_cycle = None  # type: ignore

__all__ = ("CLIP_OT_camera_tracking_coordinator",)


class CLIP_OT_camera_tracking_coordinator(Operator):
    """Modaler Ablauf: FIND → DETECT → TRACK; Solve-Test entfernt.

    Moduswahl über Scene['kc_coord_mode']:
      - 'classic' (Default): alter Modal-Flow FIND→DETECT→TRACK
      - 'orchestrator': neuer, kompakter STRM-basierten Ablauf (einmalig)
    """

    bl_idname = "clip.camera_tracking_coordinator"
    bl_label = "Camera Tracking Coordinator"
    bl_options = {"REGISTER", "UNDO"}

    _timer: object | None = None
    phase: str = "FIND"
    detect_started: bool = False
    track_started: bool = False
    # Clean vor dem nächsten Find einplanen nach einem Track-Durchlauf
    needs_clean_before_solve: bool = False

    def _finish(self, context, msg: str = "", cancel: bool = False):
        try:
            if self._timer:
                context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        self._timer = None
        if msg:
            self.report({'WARNING' if cancel else 'INFO'}, msg)
        return {'CANCELLED' if cancel else 'FINISHED'}

    def _run_orchestrator_once(self, context):
        scn = context.scene
        if run_full_cycle is None:
            return self._finish(context, "Orchestrator nicht verfügbar", cancel=True)
        try:
            # Optional: Bootstrap für saubere Defaults
            try:
                bpy.ops.clip.bootstrap_cycle()
            except Exception:
                if CLIP_OT_bootstrap_cycle is not None:
                    try:
                        bpy.utils.register_class(CLIP_OT_bootstrap_cycle)
                    except Exception:
                        pass
                    CLIP_OT_bootstrap_cycle().execute(context)
            # Orchestrator ausführen (synchron)
            res = run_full_cycle(context, tiles=(4, 6), markers_total=int(scn.get("marker_target", 250)))
            scn["kc_last_orchestrator"] = res
            self.report({'INFO'}, "Orchestrator abgeschlossen")
        except Exception as exc:
            return self._finish(context, f"Orchestrator-Fehler: {exc}", cancel=True)
        return {'FINISHED'}

    def execute(self, context):
        # Moduswahl: orchestrator (neuer Ablauf) oder classic (bestehender Modal-Flow)
        mode = str(context.scene.get("kc_coord_mode", "classic")).lower()
        if mode == "orchestrator":
            return self._run_orchestrator_once(context)

        # 1) Bootstrap immer zuerst ausführen
        try:
            bpy.ops.clip.bootstrap_cycle()
            self.report({'INFO'}, "Bootstrap ausgeführt (via bpy.ops)")
        except Exception as exc:
            # Fallback: direkter Klassenaufruf
            try:
                if CLIP_OT_bootstrap_cycle is not None:
                    try:
                        bpy.utils.register_class(CLIP_OT_bootstrap_cycle)
                    except Exception:
                        pass
                    op = CLIP_OT_bootstrap_cycle()
                    op.execute(context)
                    self.report({'INFO'}, "Bootstrap ausgeführt (direkter Fallback)")
                else:
                    self.report({'WARNING'}, f"Bootstrap konnte nicht über bpy.ops gestartet werden ({exc}) und Fallback ist nicht verfügbar.")
            except Exception as exc2:
                self.report({'WARNING'}, f"Bootstrap-Fallback fehlgeschlagen: {exc2}")

        # 2) Modal‑Loop initialisieren
        self.phase = "FIND"
        self.detect_started = False
        self.track_started = False
        self.needs_clean_before_solve = False
        wm = context.window_manager
        win = getattr(context, "window", None) or getattr(bpy.context, "window", None)
        try:
            self._timer = wm.event_timer_add(0.10, window=win) if win else wm.event_timer_add(0.10)
        except Exception:
            self._timer = wm.event_timer_add(0.10)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            return self._finish(context, "Abgebrochen", cancel=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scn = context.scene
        try:
            print(f"[Coord] phase={self.phase}")
        except Exception:
            pass

        # PHASE: FIND (Find Low & Jump)
        if self.phase == "FIND":
            try:
                bpy.ops.clip.find_low_and_jump()
                print(f"[Coord] find_low invoked; scene.tco_last_findlowjump={scn.get('tco_last_findlowjump')}")
            except Exception as exc:
                return self._finish(context, f"FindLow konnte nicht gestartet werden: {exc}", cancel=True)
            data = scn.get("tco_last_findlowjump") or {}
            status = str((data or {}).get("status", "")).upper()
            if status == "OK":
                # Frame gefunden → weiter zu DETECT
                self.phase = "DETECT"
                self.detect_started = False
                self.track_started = False
                return {'RUNNING_MODAL'}
            if status in {"NONE", ""}:
                # Kein weiterer Low‑Marker‑Frame → Coordinator sauber beenden
                info = "Kein weiterer Low‑Marker‑Frame gefunden. Coordinator beendet."
                print(f"[Coord] {info}")
                return self._finish(context, info, cancel=False)
            # Unerwarteter Status → erneut versuchen
            self.report({'WARNING'}, f"FindLow unerwarteter Status: {status} data={data}")
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE: DETECT
        if self.phase == "DETECT":
            if not self.detect_started:
                try:
                    scn["tco_detect_active"] = False
                except Exception:
                    pass
                try:
                    bpy.ops.clip.detect_cycle('INVOKE_DEFAULT')
                    self.detect_started = True
                    self.report({'INFO'}, "Detect gestartet")
                except Exception as exc:
                    return self._finish(context, f"Detect konnte nicht gestartet werden: {exc}", cancel=True)
                return {'RUNNING_MODAL'}
            if bool(scn.get("tco_detect_active", False)):
                return {'RUNNING_MODAL'}
            res = scn.get("tco_last_detect_cycle") or {}
            count_info = res.get("count") or {}
            status = str(count_info.get("status", "")).upper()
            if status == "ENOUGH":
                self.phase = "TRACK"
                self.track_started = False
                return {'RUNNING_MODAL'}
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        # PHASE: TRACK
        if self.phase == "TRACK":
            if CLIP_OT_bidirectional_track is None:
                self.report({'WARNING'}, "Bidirectional-Track nicht verfügbar – übersprungen")
                self.phase = "FIND"
                return {'RUNNING_MODAL'}
            if not self.track_started:
                try:
                    bpy.utils.register_class(CLIP_OT_bidirectional_track)
                except Exception:
                    pass
                try:
                    bpy.ops.clip.bidirectional_track('INVOKE_DEFAULT')
                    self.track_started = True
                    self.report({'INFO'}, "Track gestartet")
                except Exception as exc:
                    self.report({'WARNING'}, f"Track konnte nicht gestartet werden: {exc}")
                    self.phase = "FIND"
                return {'RUNNING_MODAL'}
            if bool(scn.get("bidi_active", False)):
                return {'RUNNING_MODAL'}
            result = str(scn.get("bidi_result", ""))
            if result and result != "OK":
                self.report({'WARNING'}, f"Track Ergebnis: {result}")
            else:
                self.report({'INFO'}, "Track abgeschlossen")
            # Nach TRACK: Clean vor dem nächsten Find einplanen
            self.needs_clean_before_solve = True
            self.phase = "FIND"
            return {'RUNNING_MODAL'}

        return self._finish(context, f"Unbekannte Phase: {self.phase}", cancel=True)


def register():
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.register_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass
    bpy.utils.register_class(CLIP_OT_camera_tracking_coordinator)


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_camera_tracking_coordinator)
    except Exception:
        pass
    if CLIP_OT_bidirectional_track is not None:
        try:
            bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
        except Exception:
            pass
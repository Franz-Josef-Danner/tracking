# Helper/optimize_tracking_modal.py
# Minimal, robust: Operator + Fallback-Funktion für den Tracking-Optimizer.

from __future__ import annotations
import bpy


__all__ = [
    "CLIP_OT_optimize_tracking_modal",
    "run_optimize_tracking_modal",
]


class CLIP_OT_optimize_tracking_modal(bpy.types.Operator):
    """Modaler Helper, um auf dem aktuellen Frame Optimierungs-Schritte auszuführen.
    Wird vom Tracking-Coordinator bei Repeat-Sättigung (>=10) gestartet.
    """
    bl_idname = "clip.optimize_tracking_modal"
    bl_label = "Optimize Tracking (Modal)"
    bl_options = {"REGISTER", "INTERNAL"}

    _timer = None

    # --- interne Hilfen -------------------------------------------------------
    def _optimize_once(self, context: bpy.types.Context) -> None:
        """Hier deine eigentlichen Optimize-Schritte einfügen.
        Platzhalter: falls verfügbar, den Marker-Helper ausführen.
        """
        # Beispiel: vorhandenen Helper-Operator aufrufen (falls registriert)
        try:
            bpy.ops.clip.marker_helper_main("EXEC_DEFAULT")
        except Exception:
            pass

        # Weitere typische Stellen, die hier Sinn machen könnten:
        # - Tracker-Parameter nachschärfen (Pattern/Search/Motion etc.)
        # - fehlerhafte Marker maskieren/entmuten
        # - kurze Tracks kappen
        # - lokales Detect/Track-Rekick o. Ä.

    def _finish(self, context: bpy.types.Context) -> None:
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
        self._timer = None

    # --- Blender Hooks --------------------------------------------------------
    def invoke(self, context: bpy.types.Context, event):
        # Sicherstellen, dass wir im CLIP_EDITOR sind und ein Clip aktiv ist
        area_ok = (context.area is not None) and (context.area.type == "CLIP_EDITOR")
        clip_ok = getattr(context.space_data, "clip", None) is not None
        if not (area_ok and clip_ok):
            self.report({"ERROR"}, "Clip Editor/Clip nicht aktiv.")
            return {"CANCELLED"}

        # kleiner Timer → kurzer, berechenbarer Modal-Durchlauf
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.15, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event):
        if event.type == "ESC":
            self._finish(context)
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Ein einziger, kurzer Optimize-Pass (reicht für den Coordinator-Handoff)
        try:
            self._optimize_once(context)
        except Exception as ex:
            # Soft-fail: wir beenden trotzdem sauber
            print(f"[OptimizeHelper] Exception: {ex}")

        self._finish(context)
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Fallback-API: direkte Funktionsschnittstelle (nicht-modal)
# Wird vom Coordinator genutzt, wenn der Operator (noch) nicht registriert ist.
# -----------------------------------------------------------------------------
def run_optimize_tracking_modal(context: bpy.types.Context | None = None) -> None:
    ctx = context or bpy.context
    scn = ctx.scene
    print(f"[OptimizeHelper] running on frame {scn.frame_current}")

    # Gleiche Schritte wie im Operator – aber synchron und ohne Timer
    try:
        bpy.ops.clip.marker_helper_main("EXEC_DEFAULT")
    except Exception:
        pass
    # Platz für weitere direkte Schritte (Parameter-Tweaks etc.)


# Optional: lokale Registrierung (praktisch fürs Einzeltesten dieser Datei)
def register():
    try:
        bpy.utils.register_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass


def unregister():
    try:
        bpy.utils.unregister_class(CLIP_OT_optimize_tracking_modal)
    except Exception:
        pass

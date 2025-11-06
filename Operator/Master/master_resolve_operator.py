# Operator/Master/master_resolve_operator_modal.py
from __future__ import annotations
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty

# --- Imports aus Ihrem Add-on ---
try:
    from ...Helper.refine_intrinsics import (
        refine_intrinsics_reset,
        refine_intrinsics_focal_length_on,
        refine_intrinsics_principal_point_on,
        refine_intrinsics_radial_distortion_on,
    )
    from ...Helper.get_average_error import get_average_error
    from ...Helper.clean_error_tracks import clean_error_tracks
    from ...Helper.low_marker_frame import find_first_weak_frame
except Exception as e:
    raise ImportError(f"[master_resolve_operator] Fehlende oder fehlerhafte Add-on-Module: {e}")

# -------------------------------------------------------------------------
# Bestehende Hilfsfunktionen unverändert übernommen
# -------------------------------------------------------------------------
# (gleiche Funktionen _solve_camera_invoke_default, _check_and_filter, _find_and_dispatch_cycle, _phase_execute)

# ... [dein Originalcode für Hilfsfunktionen bleibt exakt gleich] ...


# -------------------------------------------------------------------------
# Modal Master Resolve Operator mit Timer
# -------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Führt die Master-Resolve-Sequenz modal mit Timer aus, um UI-Freezes zu vermeiden."""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master (modal)"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: BoolProperty(
        name="Verbose Logs",
        default=True,
        description="Ausführliche UI-Hinweise (ohne Konsole) aktivieren",
    )

    _timer = None
    _phase = 0
    _phases = None
    _context_cache = None

    def log(self, msg: str) -> None:
        if getattr(self, "verbose", False):
            self.report({'INFO'}, msg)

    def invoke(self, context, event):
        self._context_cache = context
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)  # 0.5 Sekunden Tick
        wm.modal_handler_add(self)
        self._phase = 0
        self._phases = [
            ("Phase 1: refine_intrinsics_reset", refine_intrinsics_reset),
            ("Phase 2: refine_intrinsics_focal_length_on", refine_intrinsics_focal_length_on),
            ("Phase 3: refine_intrinsics_principal_point_on", refine_intrinsics_principal_point_on),
            ("Phase 4: refine_intrinsics_radial_distortion_on", refine_intrinsics_radial_distortion_on),
        ]
        self.log("Master Resolve gestartet (modal).")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.log("Abgebrochen durch Benutzer.")
            self._cleanup(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            try:
                if self._phase >= len(self._phases):
                    # Nach letzter Phase finale Prüfung
                    self._finalize(context)
                    self._cleanup(context)
                    return {'FINISHED'}

                label, fn = self._phases[self._phase]
                self.log(label)

                delegated = _phase_execute(context, fn)
                if delegated:
                    self.report({'INFO'}, f"Master-Cycle gestartet ({label}).")
                    self._cleanup(context)
                    return {'FINISHED'}

                self._phase += 1
                return {'RUNNING_MODAL'}

            except Exception as e:
                self.report({'ERROR'}, f"Fehler in Phase {self._phase + 1}: {e}")
                self._cleanup(context)
                return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def _finalize(self, context):
        """Letzte Fehlerprüfung nach allen Phasen (unverändert übernommen)."""
        try:
            clip = getattr(getattr(context, "space_data", None), "clip", None)
            if clip is None and bpy.data.movieclips:
                clip = bpy.data.movieclips[0]
            if clip is None:
                self.report({'ERROR'}, "Kein MovieClip im aktuellen Kontext gefunden.")
                return

            avg_err = get_average_error(clip)
            self.log(f"Finaler Fehler: {avg_err}")

            max_err = float(context.scene.max_error_value)
            if avg_err > max_err:
                self.log(f"Fehler ({avg_err}) > Grenzwert ({max_err}) – starte Fallbacks")
                _check_and_filter(context, avg_err)
                if _find_and_dispatch_cycle(context):
                    self.report({'INFO'}, "Master-Cycle gestartet (nach Final-Fallback).")
                    return
                bpy.ops.kaiserlich_tracker.master_solve_modal('INVOKE_DEFAULT')
                avg_err = get_average_error(clip)
                if avg_err > max_err:
                    self.report({'WARNING'}, f"Fehler bleibt zu hoch ({avg_err} > {max_err})")
            else:
                self.report({'INFO'}, "Master Resolve erfolgreich abgeschlossen.")
        except Exception as e:
            self.report({'ERROR'}, f"Finalisierung fehlgeschlagen: {e}")

    def _cleanup(self, context):
        """Timer entfernen."""
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        self._timer = None
        self._context_cache = None


# --- Solve Modal bleibt unverändert ---
class KAISERLICHTRACKER_OT_master_solve_modal(bpy.types.Operator):
    """Startet den Camera Solve und wartet modal, bis er abgeschlossen ist."""
    bl_idname = "kaiserlich_tracker.master_solve_modal"
    bl_label = "Solve Camera (modal blockierend)"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        try:
            bpy.ops.clip.solve_camera('EXEC_DEFAULT')
        except Exception as e:
            self.report({'ERROR'}, f"Solve-Start fehlgeschlagen: {e}")
            return {'CANCELLED'}

        clip = getattr(context.space_data, "clip", None)
        if clip is None and bpy.data.movieclips:
            clip = bpy.data.movieclips[0]

        if clip and getattr(clip.tracking, "reconstruction", None) and clip.tracking.reconstruction.is_valid:
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Solve unvollständig oder fehlgeschlagen.")
            return {'CANCELLED'}


# --- Registration ---
classes = (
    KAISERLICHTRACKER_OT_master_resolve_operator,
    KAISERLICHTRACKER_OT_master_solve_modal,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "max_error_value"):
        bpy.types.Scene.max_error_value = bpy.props.FloatProperty(
            name="Max Error Value",
            description="Fehler-Grenzwert zur Track-Filterung",
            default=1.0,
            min=0.0,
            soft_min=0.0,
        )

def unregister():
    if hasattr(bpy.types.Scene, "max_error_value"):
        try:
            del bpy.types.Scene.max_error_value
        except Exception:
            pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

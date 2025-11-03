# resolve_operator.py
# Copyright (...)
# Zweck: Löst die Kamera iterativ und verfeinert Intrinsics gemäß vordefiniertem Eskalationspfad.
# Erwartete Abhängigkeiten (in Ihrem Add-on vorhanden):
#   ..Helper/refine_intrinsics.py    -> refine_intrinsics_reset, refine_intrinsics_focal_length_on,
#                                     refine_intrinsics_principal_point_on, refine_intrinsics_radial_distortion_on
#   ..Helper/get_average_error.py    -> get_average_error
#   ..Helper/filter_tracks.py        -> filter_problematic_tracks
#   ..Helper/low_marker_frame.py     -> find_first_weak_frame
#
# Nutzung: F3 -> "Kaiserlich: Resolve Master" ausführen
# Hinweis: Szene-Eigenschaft scene.max_error_value (FloatProperty) wird vorausgesetzt.

from __future__ import annotations
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty

# --- Imports aus Ihrem Add-on ---
# Passen Sie die Paketpfade ggf. an Ihr Add-on-Package an (z. B. from ...Helper...)!
try:
    from ..Helper.refine_intrinsics import (
        refine_intrinsics_reset,
        refine_intrinsics_focal_length_on,
        refine_intrinsics_principal_point_on,
        refine_intrinsics_radial_distortion_on,
    )
    from ..Helper.get_average_error import get_average_error
    from ..Helper.filter_tracks import filter_problematic_tracks
    from ..Helper.low_marker_frame import find_first_weak_frame
except Exception as e:
    # Harte, frühe Fehlermeldung zwecks Diagnose fehlender Module
    raise ImportError(f"[resolve_operator] Fehlende oder fehlerhafte Add-on-Module: {e}")


def _solve_camera_invoke_default(context: bpy.types.Context) -> None:
    """
    Standardisierte Ausführung von Blender Solve-Operator mit INVOKE_DEFAULT.
    Wir laufen bewusst synchron; falls UI-Kontext fehlt, fallback auf EXEC_DEFAULT.
    """
    def _get_clip_context(ctx: bpy.types.Context):
        """Sucht oder konstruiert einen gültigen Clip-Editor-Kontext für bpy.ops.clip.*"""
        # Prüfen, ob aktueller Context bereits Clip enthält
        if hasattr(ctx, "space_data") and getattr(ctx.space_data, "clip", None):
            return ctx

        # Andernfalls passenden Bereich suchen
        for area in bpy.context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = bpy.context.copy()
                        override["area"] = area
                        override["region"] = region
                        override["space_data"] = area.spaces.active
                        return override
        # Fallback: direkter Kontext
        return ctx

    # Sicheren Kontext beschaffen
    override = _get_clip_context(context)

    # Solve-Versuch mit Override
    try:
        bpy.ops.clip.solve_camera(override, 'INVOKE_DEFAULT')
    except RuntimeError:
        try:
            bpy.ops.clip.solve_camera(override, 'EXEC_DEFAULT')
        except Exception as e:
            print(f"[resolve_operator] Solve-Aufruf fehlgeschlagen: {e}")


def _check_and_filter(context: bpy.types.Context, avg_err: float) -> float:
    """
    Prüft Fehler vs. Scene.max_error_value, filtert problematische Tracks,
    wenn Grenzwert überschritten. Gibt den (ggf. unveränderten) Fehler zurück.
    """
    scene = context.scene

    # Validierung: Property muss existieren und sinnvoll sein
    if not hasattr(scene, "max_error_value"):
        raise AttributeError(
            "[resolve_operator] scene.max_error_value ist nicht definiert. "
            "Bitte FloatProperty in Ihrem Add-on registrieren."
        )

    max_err = float(scene.max_error_value)

    # Nur wenn überschritten, filtern (Faktor 2 laut Vorgabe)
    if avg_err > max_err:
        threshold = avg_err * 2.0
        filter_problematic_tracks(context, threshold)
    return avg_err


def _find_and_dispatch_cycle(context: bpy.types.Context) -> bool:
    """
    Sucht einen schwachen Frame. Falls vorhanden, delegiert an den Master-Cycle-Operator.
    Rückgabe: True -> Cycle gestartet; False -> kein schwacher Frame gefunden.
    """
    weak_frame = find_first_weak_frame(context)
    if weak_frame is not None:
        # Master Cycle triggern
        try:
            res = bpy.ops.kaiserlichtracker.master_cycle('INVOKE_DEFAULT')
        except Exception:
            # Fallback EXEC
            res = bpy.ops.kaiserlichtracker.master_cycle('EXEC_DEFAULT')
        print(f"[resolve_operator] Master-Cycle gestartet, Operator-Result: {res}")
        return True
    return False


def _phase_execute(context: bpy.types.Context, phase_fn) -> bool:
    """
    Führt eine Verfeinerungsphase aus:
      1) phase_fn() aufrufen (z. B. reset / focal / principal / radial)
      2) Solve
      3) get_average_error
      4) ggf. filter_tracks
      5) find_first_weak_frame -> ggf. Master-Cycle
    Rückgabe: True -> Prozess wurde an Master-Cycle übergeben (Finished für diese Pipeline)
             False -> Kein schwacher Frame, weiter eskalieren
    """
    # 1) Phase konfigurieren
    phase_fn(context)

    # 2) Solve
    _solve_camera_invoke_default(context)

    # 3) Fehler messen
    avg_err = get_average_error(context)

    # 4) Prüfen/Filtern
    _check_and_filter(context, avg_err)

    # 5) Weak Frame prüfen und ggf. Master-Cycle starten
    delegated = _find_and_dispatch_cycle(context)
    return delegated


class KAISERLICHTRACKER_OT_resolve_operator(Operator):
    """Führt die Master-Resolve-Sequenz aus (Reset -> Focal -> Principal -> Radial) mit Fehlerprüfung und bedingtem Cycle-Dispatch."""
    bl_idname = "kaiserlich_tracker.resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: BoolProperty(
        name="Verbose Logs",
        default=True,
        description="Ausführliche Konsolenlogs aktivieren",
    )

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[resolve_operator] {msg}")

    def execute(self, context: bpy.types.Context):
        try:
            # === Phase 1: RESET ===
            self.log("Phase 1: refine_intrinsics_reset")
            delegated = _phase_execute(context, refine_intrinsics_reset)
            if delegated:
                self.report({'INFO'}, "Master-Cycle gestartet (nach RESET).")
                return {'FINISHED'}

            # === Phase 2: FOCAL LENGTH ===
            self.log("Phase 2: refine_intrinsics_focal_length_on")
            delegated = _phase_execute(context, refine_intrinsics_focal_length_on)
            if delegated:
                self.report({'INFO'}, "Master-Cycle gestartet (nach FOCAL).")
                return {'FINISHED'}

            # === Phase 3: PRINCIPAL POINT ===
            self.log("Phase 3: refine_intrinsics_principal_point_on")
            delegated = _phase_execute(context, refine_intrinsics_principal_point_on)
            if delegated:
                self.report({'INFO'}, "Master-Cycle gestartet (nach PRINCIPAL POINT).")
                return {'FINISHED'}

            # === Phase 4: RADIAL DISTORTION ===
            self.log("Phase 4: refine_intrinsics_radial_distortion_on")
            _ = _phase_execute(context, refine_intrinsics_radial_distortion_on)
            # Nach letzter Phase wird NICHT weiter eskaliert; Prozess endet hier,
            # unabhängig davon, ob delegiert wurde oder nicht. Falls delegiert,
            # wäre oben bereits FINISHED zurückgekehrt.

            self.report({'INFO'}, "Master-Resolve abgeschlossen.")
            return {'FINISHED'}

        except AttributeError as e:
            self.report({'ERROR'}, f"Konfigurationsfehler: {e}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Unerwarteter Fehler: {e}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return self.execute(context)


# --- Operator Alias für Aufrufkürzel (optional) ---
# Damit der Master-Cycle via bpy.ops.kaiserlichtracker.master_cycle existiert,
# muss der referenzierte Operator die bl_idname "kaiserlichtracker.master_cycle" besitzen.
# Wir importieren ihn oben nur, um sicherzustellen, dass das Modul geladen ist.
# Der eigentliche Aufruf erfolgt über bpy.ops.kaiserlichtracker.master_cycle(...).

# --- Registration ---
classes = (
    KAISERLICHTRACKER_OT_resolve_operator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Defensive: Scene-Property sicherstellen, falls Add-on-Init sie noch nicht gesetzt hat.
    if not hasattr(bpy.types.Scene, "max_error_value"):
        bpy.types.Scene.max_error_value = bpy.props.FloatProperty(
            name="Max Error Value",
            description="Fehler-Grenzwert zur Track-Filterung",
            default=1.0,
            min=0.0,
            soft_min=0.0,
        )
        print("[resolve_operator] Hinweis: scene.max_error_value wurde temporär registriert.")

def unregister():
    # Property nur entfernen, wenn wir sie hier temporär angelegt haben.
    # Wenn Ihr Add-on sie zentral registriert, entfernen Sie den folgenden Block.
    if hasattr(bpy.types.Scene, "max_error_value"):
        try:
            del bpy.types.Scene.max_error_value
        except Exception:
            pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

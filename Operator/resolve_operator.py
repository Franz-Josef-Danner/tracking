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
    print("\n[resolve_operator][DEBUG] _solve_camera_invoke_default() gestartet")
    print(f"[resolve_operator][DEBUG] context.area: {getattr(context, 'area', None)}")
    print(f"[resolve_operator][DEBUG] context.space_data: {getattr(context, 'space_data', None)}")
    if getattr(context, 'space_data', None):
        print(f"[resolve_operator][DEBUG] context.space_data.type: {getattr(context.space_data, 'type', None)}")
        clip_dbg = getattr(context.space_data, 'clip', None)
        print(f"[resolve_operator][DEBUG] context.space_data.clip: {clip_dbg}")
        if clip_dbg:
            print(f"[resolve_operator][DEBUG] clip.name: {getattr(clip_dbg, 'name', None)}")
            print(f"[resolve_operator][DEBUG] clip.tracking: {getattr(clip_dbg, 'tracking', None)}")
    # 1) Clip-Editor-Area/Region/Speicher suchen
    area = None
    region = None
    space = None

    # a) bevorzugt: aktueller Context ist bereits CLIP_EDITOR
    if getattr(context, "area", None) and getattr(context.area, "type", "") == 'CLIP_EDITOR':
        area = context.area
        # passende WINDOW-Region suchen
        for r in area.regions:
            if r.type == 'WINDOW':
                region = r
                break
        space = area.spaces.active if area.spaces else None

    # b) sonst: in aktueller Screen nach CLIP_EDITOR suchen
    if area is None:
        for a in bpy.context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                area = a
                for r in a.regions:
                    if r.type == 'WINDOW':
                        region = r
                        break
                space = a.spaces.active if a.spaces else None
                break

    # c) Wenn kein CLIP_EDITOR existiert, abbrechen
    if area is None or region is None or space is None:
        print("[resolve_operator] ❌ Kein CLIP_EDITOR-Kontext verfügbar – Solve abgebrochen.")
        raise RuntimeError("No CLIP_EDITOR context available")

    # 2) temp_override verwenden und Solve durchführen
    try:
        print(f"[resolve_operator][DEBUG] Solve-Kontext gefunden -> area={area}, region={region}, space={space}")
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            print("[resolve_operator][DEBUG] bpy.ops.clip.solve_camera('INVOKE_DEFAULT') wird ausgeführt …")
            bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
            print("[resolve_operator][DEBUG] Solve abgeschlossen (INVOKE_DEFAULT).")

    except RuntimeError:
        # Fallback: EXEC_DEFAULT (z. B. in Headless/ohne UI-Flow)
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            print("[resolve_operator][DEBUG] Fallback: bpy.ops.clip.solve_camera('EXEC_DEFAULT') wird ausgeführt …")
            bpy.ops.clip.solve_camera('EXEC_DEFAULT')
            print("[resolve_operator][DEBUG] Solve abgeschlossen (EXEC_DEFAULT).")

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
    print("\n[resolve_operator][DEBUG] === _phase_execute() gestartet ===")

    # 0) Kontextdiagnose
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    print(f"[resolve_operator][DEBUG] Aktueller Space: {space}")
    print(f"[resolve_operator][DEBUG] Aktueller Clip: {clip}")
    if clip:
        print(f"[resolve_operator][DEBUG] Clip hat Tracking: {hasattr(clip, 'tracking')}")
        print(f"[resolve_operator][DEBUG] Tracking-Objekt: {getattr(clip, 'tracking', None)}")

    # 1) Phase konfigurieren
    print(f"[resolve_operator][DEBUG] Phase-Funktion: {phase_fn.__name__}")
    try:
        phase_fn(context)
    except Exception as e:
        print(f"[resolve_operator][ERROR] Fehler in Phase-Funktion {phase_fn.__name__}: {e}")
        raise

    # 2) Solve
    print("[resolve_operator][DEBUG] -> Starte Solve-Phase (modal blockierend) …")
    try:
        bpy.ops.kaiserlich_tracker.solve_modal('INVOKE_DEFAULT')
    except Exception as e:
        print(f"[resolve_operator][ERROR] Modal Solve fehlgeschlagen: {e}")
        raise

    # 3) Fehler messen
    print("[resolve_operator][DEBUG] -> Ermittle durchschnittlichen Fehler …")
    try:
        # Clip direkt aus Context ziehen, statt Context zu übergeben
        clip = getattr(getattr(context, "space_data", None), "clip", None)
        if clip is None:
            clip = getattr(bpy.context, "edit_movieclip", None)
        if clip is None and bpy.data.movieclips:
            clip = bpy.data.movieclips[0]

        if clip is None:
            raise AttributeError("Kein MovieClip im aktuellen Kontext gefunden.")

        print(f"[resolve_operator][DEBUG] get_average_error() Clip: {clip.name}")
        avg_err = get_average_error(clip)
        print(f"[resolve_operator][DEBUG] Durchschnittlicher Fehler (avg_err): {avg_err}")
    except Exception as e:
        print(f"[resolve_operator][ERROR] Fehler in get_average_error(): {e}")
        raise

    # 4) Prüfen/Filtern
    print("[resolve_operator][DEBUG] -> Prüfe/Filtere Tracks …")
    _check_and_filter(context, avg_err)

    # 5) Weak Frame prüfen und ggf. Master-Cycle starten
    print("[resolve_operator][DEBUG] -> Suche schwachen Frame …")
    delegated = _find_and_dispatch_cycle(context)
    print(f"[resolve_operator][DEBUG] Delegated? {delegated}")


# -------------------------------------------------------------------------
# Modal Solve Operator (führt Solve asynchron aus und wartet blockierend)
# -------------------------------------------------------------------------

class KAISERLICHTRACKER_OT_solve_modal(bpy.types.Operator):
    """Startet den Camera Solve und wartet modal, bis er abgeschlossen ist."""
    bl_idname = "kaiserlich_tracker.solve_modal"
    bl_label = "Solve Camera (modal blockierend)"
    bl_options = {'REGISTER', 'INTERNAL'}

    _timer = None

    def execute(self, context):
        print("[solve_modal] Starte Solve …")
        try:
            bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'ERROR'}, f"Solve-Start fehlgeschlagen: {e}")
            return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            clip = getattr(context.space_data, "clip", None)
            if clip is None and bpy.data.movieclips:
                clip = bpy.data.movieclips[0]

            if clip and clip.tracking.reconstruction.is_valid:
                print("[solve_modal] Solve abgeschlossen.")
                self.cancel(context)
                return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
        print("[solve_modal] Timer gestoppt.")

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
    KAISERLICHTRACKER_OT_solve_modal,
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

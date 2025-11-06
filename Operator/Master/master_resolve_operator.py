# Operator/Master/master_resolve_operator.py
# Copyright (...)
# Zweck: Löst die Kamera iterativ und verfeinert Intrinsics gemäß vordefiniertem Eskalationspfad.

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

def _solve_camera_invoke_default(context: bpy.types.Context) -> None:
    """
    Standardisierte Ausführung von Blender Solve-Operator mit INVOKE_DEFAULT.
    Fällt bei fehlendem UI-Kontext auf EXEC_DEFAULT zurück.
    """
    # 1) Clip-Editor-Area/Region/Speicher suchen
    area = None
    region = None
    space = None

    # a) bevorzugt: aktueller Context ist bereits CLIP_EDITOR
    if getattr(context, "area", None) and getattr(context.area, "type", "") == 'CLIP_EDITOR':
        area = context.area
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
        raise RuntimeError("No CLIP_EDITOR context available")

    # 2) temp_override verwenden und Solve durchführen
    try:
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.solve_camera('INVOKE_DEFAULT')
    except RuntimeError:
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.solve_camera('EXEC_DEFAULT')

def _check_and_filter(context: bpy.types.Context, avg_err: float) -> float:
    """
    Prüft Fehler vs. Scene.max_error_value, filtert problematische Tracks,
    wenn Grenzwert überschritten. Gibt den (ggf. unveränderten) Fehler zurück.
    """
    scene = context.scene

    if not hasattr(scene, "max_error_value"):
        raise AttributeError(
            "[master_resolve_operator] scene.max_error_value ist nicht definiert. "
            "Bitte FloatProperty in Ihrem Add-on registrieren."
        )

    max_err = float(scene.max_error_value)

    # --- Fehler prüfen & Schwellenwert absichern ---
    try:
        val = float(avg_err)
    except (TypeError, ValueError):
        val = 0.0

    if val <= 0.0 or not (val == val):  # NaN-Schutz
        print(f"[Resolve][Error-Filter] ⚠️ Ungültiger Fehlerwert ({avg_err}); setze 20.0 als Threshold.")
        try:
            result = clean_error_tracks(context, 20.0)
            print(f"[Resolve][Error-Filter] 🧹 Cleaned error tracks mit Threshold=20.0 → Result: {result}")
        except Exception as e:
            print(f"[Resolve][Error-Filter] ❌ Fehler beim Clean: {e}")
        return 20.0

    # Nur wenn überschritten, filtern (Faktor 2 laut Vorgabe)
    if val > max_err:
        threshold = val * 2.0
        if threshold <= 0.0 or threshold == float("inf"):
            threshold = 20.0
        print(f"[Resolve][Error-Filter] 🚀 Fehler {val:.3f} > Max {max_err:.3f} → Filter starte mit Threshold={threshold:.3f}")
        try:
            result = clean_error_tracks(context, threshold)
            print(f"[Resolve][Error-Filter] 🧹 Cleaned error tracks (Threshold={threshold:.3f}) → Result: {result}")
        except Exception as e:
            print(f"[Resolve][Error-Filter] ❌ Fehler beim Clean: {e}")
    else:
        print(f"[Resolve][Error-Filter] ✅ Fehler {val:.3f} ≤ Max {max_err:.3f} → kein Filter nötig.")

    return val

def _find_and_dispatch_cycle(context: bpy.types.Context) -> bool:
    """
    Sucht einen schwachen Frame. Falls vorhanden, delegiert an den Master-Cycle-Operator.
    Rückgabe: True -> Cycle gestartet; False -> kein schwacher Frame gefunden.
    """
    weak_frame = find_first_weak_frame(context)
    if weak_frame is not None:
        try:
            bpy.ops.kaiserlich_tracker.master_cycle_operator('INVOKE_DEFAULT')
            return True
        except Exception:
            return False
    return False

def _phase_execute(context: bpy.types.Context, phase_fn) -> bool:
    """
    Führt eine Verfeinerungsphase aus:
      1) phase_fn() aufrufen (z. B. reset / focal / principal / radial)
      2) Solve
      3) get_average_error
      4) ggf. filter_tracks
      5) find_first_weak_frame -> ggf. Master-Cycle
    Rückgabe: True -> Prozess wurde an Master-Cycle übergeben
             False -> Kein schwacher Frame, weiter eskalieren
    """
    # 1) Phase konfigurieren
    phase_fn(context)

    # 2) Solve
    bpy.ops.kaiserlich_tracker.master_solve_modal('INVOKE_DEFAULT')

    # 3) Fehler messen (Clip direkt aus Context ziehen)
    clip = getattr(getattr(context, "space_data", None), "clip", None)
    if clip is None:
        clip = getattr(bpy.context, "edit_movieclip", None)
    if clip is None and bpy.data.movieclips:
        clip = bpy.data.movieclips[0]
    if clip is None:
        raise AttributeError("Kein MovieClip im aktuellen Kontext gefunden.")

    avg_err = get_average_error(clip)

    # 4) Prüfen/Filtern
    _check_and_filter(context, avg_err)

    # 5) Weak Frame prüfen und ggf. Master-Cycle starten
    delegated = _find_and_dispatch_cycle(context)
    if delegated:
        return True

    return False

# -------------------------------------------------------------------------
# Modal Solve Operator (führt Solve asynchron aus und wartet blockierend)
# -------------------------------------------------------------------------

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

class KAISERLICHTRACKER_OT_master_resolve_operator(Operator):
    """Führt die Master-Resolve-Sequenz aus (Reset -> Focal -> Principal -> Radial) mit Fehlerprüfung und bedingtem Cycle-Dispatch."""
    bl_idname = "kaiserlich_tracker.master_resolve_operator"
    bl_label = "Kaiserlich: Resolve Master"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: BoolProperty(
        name="Verbose Logs",
        default=True,
        description="Ausführliche UI-Hinweise (ohne Konsole) aktivieren",
    )

    # Keine print-Ausgaben – nur UI-Reports, optional via verbose flag
    def log(self, msg: str) -> None:
        if getattr(self, "verbose", False):
            # Info-Meldung sichtbar im Statusbereich
            self.report({'INFO'}, msg)

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
            delegated = _phase_execute(context, refine_intrinsics_radial_distortion_on)
            if delegated:
                self.report({'INFO'}, "Master-Cycle gestartet (nach RADIAL DISTORTION).")
                return {'FINISHED'}

            # ----------------------------------------------
            # Erweiterte Nachbearbeitung falls keine Delegation passierte
            # ----------------------------------------------
            self.log("Finale Nachbearbeitung: Fehler erneut prüfen …")

            clip = getattr(getattr(context, "space_data", None), "clip", None)
            if clip is None and bpy.data.movieclips:
                clip = bpy.data.movieclips[0]
            if clip is None:
                self.report({'ERROR'}, "Kein MovieClip im aktuellen Kontext gefunden.")
                return {'CANCELLED'}

            avg_err = get_average_error(clip)
            self.log(f"Finaler Fehler: {avg_err}")

            max_err = float(context.scene.max_error_value)

            # Nur aktiv, wenn Fehler immer noch zu hoch und kein schwacher Frame vorhanden
            if avg_err > max_err:
                self.log(f"Fehler ({avg_err}) > Grenzwert ({max_err}) – starte Fallback-Strategie")

                # 1️⃣ Erster Fallback: Filter ohne Multiplikation
                self.log("Fallback 1: Direkter Filter mit avg_err")
                print(f"[Resolve][Fallback1] 🔧 Clean-Start mit Threshold={avg_err:.3f}")
                _check_and_filter(context, avg_err)
                print(f"[Resolve][Fallback1] ✅ Clean abgeschlossen")                if _find_and_dispatch_cycle(context):
                    self.report({'INFO'}, "Master-Cycle gestartet (nach Fallback 1).")
                    return {'FINISHED'}

                # 2️⃣ Zweiter Fallback: Solve erneut
                self.log("Fallback 2: Neuer Solve nach direktem Filter")
                print("[Resolve][Fallback2] 🔁 Solve erneut gestartet …")
                bpy.ops.kaiserlich_tracker.master_solve_modal('INVOKE_DEFAULT')
                avg_err = get_average_error(clip)
                print(f"[Resolve][Fallback2] 🔍 Neuer Fehlerwert nach Solve: {avg_err}")
                self.log(f"Fehler nach Fallback-2-Solve: {avg_err}")

                if avg_err > max_err:
                    # 3️⃣ Dritter Fallback: Filter mit max_error_value als Schwelle
                    self.log("Fallback 3: Filter mit Scene.max_error_value als Schwelle")
                    threshold = max_err
                    print(f"[Resolve][Fallback3] 🔧 Clean-Start mit Threshold={threshold:.3f}")
                    try:
                        result = clean_error_tracks(context, threshold)
                        print(f"[Resolve][Fallback3] 🧹 Cleaned error tracks (Threshold={threshold:.3f}) → Result: {result}")
                    except Exception as e:
                        print(f"[Resolve][Fallback3] ❌ Fehler beim Clean: {e}")
                    if _find_and_dispatch_cycle(context):
                        self.report({'INFO'}, "Master-Cycle gestartet (nach Fallback 3).")
                        return {'FINISHED'}

                    # Letzter Solve-Versuch
                    self.log("Fallback 3b: Letzter Solve nach hartem Filter")
                    print("[Resolve][Fallback3b] 🔁 Letzter Solve wird ausgeführt …")
                    bpy.ops.kaiserlich_tracker.master_solve_modal('INVOKE_DEFAULT')
                    avg_err = get_average_error(clip)
                    print(f"[Resolve][Fallback3b] 🔍 Fehler nach Solve: {avg_err}")
                    self.log(f"Fehler nach Fallback-3b-Solve: {avg_err}")

                    if avg_err > max_err:
                        self.report({'WARNING'}, f"Master-Resolve: Fehler bleibt zu hoch ({avg_err} > {max_err}).")
                        return {'CANCELLED'}

            # ----------------------------------------------
            # Erfolgsfall
            # ----------------------------------------------
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

# --- Registration ---
classes = (
    KAISERLICHTRACKER_OT_master_resolve_operator,
    KAISERLICHTRACKER_OT_master_solve_modal,
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

def unregister():
    # Property nur entfernen, wenn wir sie hier temporär angelegt haben.
    if hasattr(bpy.types.Scene, "max_error_value"):
        try:
            del bpy.types.Scene.max_error_value
        except Exception:
            pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

# Operator/tracking_coordtorina.py
# Minimal-Orchestrator: führt zuerst Helper/set_test_value.py aus
# und löst DANACH NUR Helper/optimize_tracking_modal aus.
# Priorität: bpy.ops.clip.optimize_tracking_modal("INVOKE_DEFAULT")
# Fallback:  Helper.run_optimize_tracking_modal(context) bzw. run_optimize_tracking_modal()

from __future__ import annotations

import bpy
import unicodedata
from typing import Set, Optional

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")

LOCK_KEY = "__detect_lock"  # bleibt für Kompatibilität, wird hier nicht genutzt


# ------------------------------------------------------------
# String-Sanitizer (defensiv gegen NBSP/Encoding-Ausreißer)
# ------------------------------------------------------------
def _sanitize_str(s) -> str:
    if isinstance(s, (bytes, bytearray)):
        try:
            s = s.decode("utf-8")
        except Exception:
            s = s.decode("latin-1", errors="replace")
    s = str(s).replace("\u00A0", " ")  # NBSP → Space
    return unicodedata.normalize("NFKC", s).strip()


def _sanitize_all_track_names(context: bpy.types.Context) -> None:
    """Bereinigt sicher alle Track-Namen im aktiven/zugeordneten MovieClip."""
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if not mc:
        return
    try:
        tracks = mc.tracking.tracks
    except Exception:
        return
    for tr in tracks:
        try:
            tr.name = _sanitize_str(tr.name)
        except Exception:
            pass


# ------------------------------------------------------------
# Optionaler, sicherer CLIP_EDITOR-Override (nur falls nötig)
# ------------------------------------------------------------
def _clip_override(context: bpy.types.Context) -> Optional[dict]:
    win = getattr(context, "window", None)
    scr = getattr(win, "screen", None) if win else None
    if not (win and scr):
        return None
    for area in scr.areas:
        if area.type == "CLIP_EDITOR":
            for region in area.regions:
                if region.type == "WINDOW":
                    return {
                        "window": win,
                        "screen": scr,
                        "area": area,
                        "region": region,
                        "space_data": area.spaces.active,
                        "scene": context.scene,
                    }
    return None


# ------------------------------------------------------------
# NEU: Pre-Optimize Hook – führt set_test_value(scene) aus
# ------------------------------------------------------------
def _pre_optimize_setup(context: bpy.types.Context) -> None:
    scn = context.scene
    # Sanity: Property-Verfügbarkeit (verhindert None/KeyErrors)
    if not hasattr(bpy.types.Scene, "marker_frame"):
        # Falls UI-Property nicht registriert ist, überspringen – kein harter Abbruch
        print("[Coordinator] [Pre] marker_frame Property nicht registriert – überspringe set_test_value.")
        return

    try:
        # Lazy-Import, kein eager import beim Add-on-Enable
        from ..Helper.set_test_value import set_test_value  # type: ignore
    except Exception as ex:
        print(f"[Coordinator] [Pre] set_test_value nicht verfügbar: {ex}")
        return

    try:
        ret = set_test_value(scn)
    except TypeError:
        # Falls alte Signatur ohne Argumente existiert
        try:
            ret = set_test_value()
        except Exception as ex2:
            print(f"[Coordinator] [Pre] set_test_value() fehlgeschlagen: {ex2}")
            return
    except Exception as ex:
        print(f"[Coordinator] [Pre] set_test_value Fehler: {ex}")
        return

    # Diagnoseausgabe: was wurde gesetzt?
    ma = scn.get("marker_adapt")
    mn = scn.get("marker_min")
    mx = scn.get("marker_max")
    print(f"[Coordinator] [Pre] set_test_value ok → marker_adapt={ma}, min={mn}, max={mx}, ret={ret}")


# ------------------------------------------------------------
# Kern: nur Optimize triggern (Operator-first, dann Fallback)
# ------------------------------------------------------------
def _run_optimize_helper(context: bpy.types.Context) -> None:
    print(f"[Coordinator] Optimize-Start auf Frame {context.scene.frame_current}")

    # 1) Versuche den registrierten Operator (bevorzugt, inkl. UI)
    try:
        if hasattr(bpy.ops.clip, "optimize_tracking_modal"):
            bpy.ops.clip.optimize_tracking_modal("INVOKE_DEFAULT")
            print("[Coordinator] bpy.ops.clip.optimize_tracking_modal → INVOKE_DEFAULT")
            return
    except Exception as ex:
        print(f"[Coordinator] Operator-Aufruf fehlgeschlagen: {ex}")

    # 2) Fallback: direkte Helper-Funktion
    try:
        from ..Helper.optimize_tracking_modal import run_optimize_tracking_modal  # type: ignore
        try:
            run_optimize_tracking_modal(context)
            print("[Coordinator] Helper.run_optimize_tracking_modal(context) ausgeführt")
        except TypeError:
            run_optimize_tracking_modal()
            print("[Coordinator] Helper.run_optimize_tracking_modal() (ohne ctx) ausgeführt")
    except Exception as ex:
        print(f"[Coordinator] Fallback-Helper nicht aufrufbar: {ex}")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Minimaler Orchestrator: Pre-Hook → Optimize-Helper."""

    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Optimize Only + PreHook)"
    bl_description = "Führt zuerst Helper/set_test_value aus, danach Helper/optimize_tracking_modal (Operator-first, Fallback auf Funktion)"
    bl_options = {"REGISTER", "UNDO"}

    # Optional: sanftes Preflight-Sanitizing aktivierbar
    sanitize_names: bpy.props.BoolProperty(
        name="Sanitize Track Names",
        default=True,
        description="Vor dem Optimize-Start Track-Namen auf Encoding-Probleme prüfen/bereinigen",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Schlank und robust: bevorzugt im CLIP_EDITOR laufen
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        # Optional: Strings entschärfen, um Unicode-Fails im Helper zu vermeiden
        if self.sanitize_names:
            try:
                _sanitize_all_track_names(context)
            except Exception as ex:
                print(f"[Coordinator] Sanitize-Namen Warnung: {ex}")

        # --- NEU: Pre-Optimize Setup (set_test_value) ---
        try:
            _pre_optimize_setup(context)
        except Exception as ex:
            print(f"[Coordinator] Pre-Setup unerwarteter Fehler: {ex}")

        # Falls der Helper Editor-Kontext braucht → Override nutzen
        override = _clip_override(context)
        if override:
            try:
                with bpy.context.temp_override(**override):
                    _run_optimize_helper(context)
            except Exception as ex:
                print(f"[Coordinator] Override-Ausführung fehlgeschlagen: {ex}")
                _run_optimize_helper(context)
        else:
            _run_optimize_helper(context)

        print("[Coordinator] Done (Optimize-only).")
        return {"FINISHED"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # execute spiegelt invoke (ohne Event) – für Scripting/Batch-Aufrufe
        return self.invoke(context, None)


# ------------------------------------------------------------
# Register/Unregister
# ------------------------------------------------------------
classes = (CLIP_OT_tracking_coordinator,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    print("[Coordinator] tracking_coordtorina registered (Optimize-only + PreHook)")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    print("[Coordinator] tracking_coordtorina unregistered")

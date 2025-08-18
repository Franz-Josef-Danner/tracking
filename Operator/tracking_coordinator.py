# Operator/tracking_coordinator.py
# Minimale Orchestrierung: Pre-Hook (set_test_value) → Operator-Aufruf
# Ausschließlich: bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')

from __future__ import annotations
import bpy
import unicodedata
from typing import Optional, Set

__all__ = ("CLIP_OT_tracking_coordinator", "register", "unregister")


# -------------------------
# Utility: String Sanitizer
# -------------------------
def _sanitize_str(s) -> str:
    if isinstance(s, (bytes, bytearray)):
        try:
            s = s.decode("utf-8")
        except Exception:
            s = s.decode("latin-1", errors="replace")
    s = str(s).replace("\u00A0", " ")
    return unicodedata.normalize("NFKC", s).strip()


def _sanitize_all_track_names(context: bpy.types.Context) -> None:
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if not mc:
        return
    try:
        for tr in mc.tracking.tracks:
            try:
                tr.name = _sanitize_str(tr.name)
            except Exception:
                pass
    except Exception:
        pass


# --------------------------------------------
# Sichere Context-Override für CLIP_EDITOR
# --------------------------------------------
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


# --------------------------------------------
# Pre-Hook: set_test_value (optional defensiv)
# --------------------------------------------
def _pre_optimize_setup(context: bpy.types.Context) -> None:
    try:
        from ..Helper.set_test_value import set_test_value  # lazy import
    except Exception as ex:
        print(f"[Coordinator] [Pre] set_test_value nicht verfügbar: {ex}")
        return

    try:
        # bevorzugt: neuere Signatur mit Szene
        set_test_value(context.scene)
    except TypeError:
        try:
            set_test_value()
        except Exception as ex2:
            print(f"[Coordinator] [Pre] set_test_value() fehlgeschlagen: {ex2}")
            return
    except Exception as ex:
        print(f"[Coordinator] [Pre] set_test_value Fehler: {ex}")
        return

    scn = context.scene
    print(f"[Coordinator] [Pre] set_test_value ok → marker_adapt={scn.get('marker_adapt')}, "
          f"min={scn.get('marker_min')}, max={scn.get('marker_max')}")


# --------------------------------------------
# Operator-Only Trigger
# --------------------------------------------
def _run_optimize_operator(context: bpy.types.Context) -> None:
    print(f"[Coordinator] Optimize-Start auf Frame {context.scene.frame_current}")

    # Harte Abhängigkeit: der Operator MUSS registriert sein
    if not hasattr(bpy.ops.clip, "optimize_tracking_modal"):
        raise RuntimeError("Operator 'clip.optimize_tracking_modal' ist nicht registriert.")

    # UI-konformer Aufruf
    bpy.ops.clip.optimize_tracking_modal('INVOKE_DEFAULT')
    print("[Coordinator] bpy.ops.clip.optimize_tracking_modal → INVOKE_DEFAULT")


class CLIP_OT_tracking_coordinator(bpy.types.Operator):
    """Minimaler Orchestrator: Pre-Hook → Optimize-Operator."""
    bl_idname = "clip.tracking_coordinator"
    bl_label = "Tracking Orchestrator (Optimize Only)"
    bl_description = "Führt set_test_value aus und startet den Operator clip.optimize_tracking_modal"
    bl_options = {"REGISTER", "UNDO"}

    sanitize_names: bpy.props.BoolProperty(
        name="Sanitize Track Names",
        default=True,
        description="Vor dem Optimize-Start Track-Namen auf Encoding-Probleme prüfen/bereinigen",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None) and (context.area.type == "CLIP_EDITOR")

    def invoke(self, context: bpy.types.Context, event) -> Set[str]:
        try:
            if self.sanitize_names:
                _sanitize_all_track_names(context)
            _pre_optimize_setup(context)

            override = _clip_override(context)
            if override:
                with bpy.context.temp_override(**override):
                    _run_optimize_operator(context)
            else:
                _run_optimize_operator(context)

            print("[Coordinator] Done (Operator-only).")
            return {"FINISHED"}

        except Exception as ex:
            self.report({'ERROR'}, f"Coordinator-Fehler: {ex}")
            return {"CANCELLED"}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Spiegelung von invoke für Scripting
        return self.invoke(context, None)


# ----------
# Register
# ----------
_classes = (CLIP_OT_tracking_coordinator,)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    print("[Coordinator] tracking_coordinator registered (Operator-only)")

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    print("[Coordinator] tracking_coordinator unregistered")

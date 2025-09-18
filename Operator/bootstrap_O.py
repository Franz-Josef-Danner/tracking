import bpy
from bpy.types import Operator

# Helper-Imports (robust mit Fallbacks)
try:
    from ..Helper.tracker_settings import apply_tracker_settings  # type: ignore
except Exception:
    apply_tracker_settings = None  # type: ignore

try:
    from ..Helper.marker_helper_main import marker_helper_main  # type: ignore
except Exception:
    marker_helper_main = None  # type: ignore

try:
    from ..Helper.reset_state import reset_for_new_cycle  # type: ignore
except Exception:
    reset_for_new_cycle = None  # type: ignore

try:
    from ..Helper.tracking_state import reset_tracking_state  # type: ignore
except Exception:
    reset_tracking_state = None  # type: ignore

_LOCK_KEY = "tco_lock"

class CLIP_OT_bootstrap_cycle(Operator):
    bl_idname = "clip.bootstrap_cycle"
    bl_label = "Bootstrap (Reset + Helpers)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scn = context.scene
        # Tracker-Settings anwenden
        try:
            if apply_tracker_settings is not None:
                scn["tco_last_tracker_settings"] = dict(apply_tracker_settings(context, scene=scn, log=True))
            else:
                scn["tco_last_tracker_settings"] = {"status": "SKIPPED", "reason": "apply_tracker_settings missing"}
        except Exception as exc:
            scn["tco_last_tracker_settings"] = {"status": "FAILED", "reason": str(exc)}
        # Marker-Helper ausführen
        try:
            if marker_helper_main is not None:
                ok, count, info = marker_helper_main(context)
                scn["tco_last_marker_helper"] = {"ok": bool(ok), "count": int(count), "info": dict(info) if hasattr(info, "items") else info}
            else:
                scn["tco_last_marker_helper"] = {"status": "SKIPPED", "reason": "marker_helper_main missing"}
        except Exception as exc:
            scn["tco_last_marker_helper"] = {"status": "FAILED", "reason": str(exc)}
        # Reset für neuen Zyklus (inkl. Log leeren)
        try:
            if reset_for_new_cycle is not None:
                reset_for_new_cycle(context, clear_solve_log=True)
        except Exception:
            pass
        # Tracking-State zurücksetzen
        try:
            if reset_tracking_state is not None:
                reset_tracking_state(context)
        except Exception:
            pass
        # Lock-Key zurücksetzen
        try:
            scn[_LOCK_KEY] = False
        except Exception:
            pass
        self.report({'INFO'}, "Bootstrap: Tracker+Marker+Reset ausgeführt")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CLIP_OT_bootstrap_cycle)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bootstrap_cycle)

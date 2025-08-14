# Operator/marker_helper_main.py
import bpy
from bpy.types import Operator

# >>> WICHTIG: Helper direkt importieren (kein bpy.ops!)
# Pfad ggf. an deine Paketstruktur anpassen:
from ..Helper.main_to_adapt import main_to_adapt

def _clip_override(ctx):
    win = getattr(ctx, "window", None)
    if not win or not getattr(win, "screen", None):
        return None
    for area in win.screen.areas:
        if area.type == 'CLIP_EDITOR':
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region:
                return {
                    'window': ctx.window,
                    'screen': ctx.screen,
                    'area': area,
                    'region': region,
                    'space_data': area.spaces.active
                }
    return None

class CLIP_OT_marker_helper_main(Operator):
    bl_idname = "clip.marker_helper_main"
    bl_label = "Marker Helper Main"
    bl_description = "Berechnet Marker-/Tracking-Zielwerte aus den Scene-Properties und startet die Kette"
    bl_options = {"REGISTER", "UNDO"}      # WICHTIG: REGISTER rein, INTERNAL raus

    factor: bpy.props.IntProperty(
        name="Faktor",
        description="Multiplikator für marker_basis → marker_adapt",
        default=4, min=1, max=999
    )

    @classmethod
    def poll(cls, context):
        area = getattr(context, "area", None)
        space = getattr(context, "space_data", None)
        return (
            area and area.type == 'CLIP_EDITOR'
            and space and getattr(space, "clip", None) is not None
        )


    def execute(self, context):
        scene = context.scene

        # --- 1) SOURCE OF TRUTH: UI-Properties aus Scene ---
        marker_basis = int(getattr(scene, "marker_frame", 25))   # Zielmarker/Frame (UI)
        frames_track = int(getattr(scene, "frames_track", 25))   # Ziel-Trackinglänge (UI)
        error_track  = float(getattr(scene, "error_track", 2.0)) # tolerierter Reproj.-Fehler (UI)

        # --- 2) Ableitungen für Marker-Zielkorridor ---
        marker_adapt = int(marker_basis * self.factor * 0.9)
        marker_min   = int(marker_adapt * 0.9)
        marker_max   = int(marker_adapt * 1.1)

        # --- 3) Persistenz für Downstream ---
        scene["marker_basis"] = int(marker_basis)
        scene["marker_adapt"] = int(marker_adapt)
        scene["marker_min"]   = int(marker_min)
        scene["marker_max"]   = int(marker_max)
        scene["frames_track"] = int(frames_track)
        scene["error_track"]  = float(error_track)

        # Legacy/Fallback-Keys (falls Altcode diese liest)
        scene["min_marker"]   = int(marker_min)
        scene["max_marker"]   = int(marker_max)

        # --- 4) repeat_frame sauber initialisieren ---
        try:
            _ = scene.repeat_frame
            scene.repeat_frame.clear()
            scene["repeat_frame_initialized"] = True
        except Exception:
            scene["repeat_frame_initialized"] = False

        # --- 5) Telemetrie ---
        msg = (f"[MarkerHelper] basis={marker_basis}, factor={self.factor} → "
               f"adapt={marker_adapt}, min={marker_min}, max={marker_max} | "
               f"frames_track={frames_track}, error_track={error_track}")
        print(msg)
        self.report({'INFO'}, msg)

        # --- 6) Nächster Schritt via HELPER (kein bpy.ops!) ---
        try:
            ok, adapt_val, op_result = main_to_adapt(
                context,
                factor=int(self.factor),
                use_override=True,   # sichert CLIP_EDITOR-Kontext via temp_override
                call_next=True,      # triggert tracker_settings
                invoke_next=True     # 'INVOKE_DEFAULT' für tracker_settings
            )
            print(f"[MarkerHelper] → main_to_adapt: ok={ok}, adapt={adapt_val}, op_result={op_result}")
            if (not ok) or (op_result and 'CANCELLED' in op_result):
                self.report({'ERROR'}, "main_to_adapt/tracker_settings fehlgeschlagen.")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"main_to_adapt (Helper) Fehler: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


# Registration
classes = (CLIP_OT_marker_helper_main,)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

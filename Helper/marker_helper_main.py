# Operator/marker_helper_main.py
import bpy

# >>> WICHTIG: Helper direkt importieren (kein bpy.ops!)
# Pfad ggf. an deine Paketstruktur anpassen:

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

class marker_helper_main():
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
        # F3 überall zulassen – wir sichern den Kontext in execute()
        return True


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

# Registration
classes = (CLIP_OT_marker_helper_main,)
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

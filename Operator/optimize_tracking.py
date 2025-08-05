import bpy

# Operator zur Anzeige des Errors im UI
class CLIP_OT_error_value(bpy.types.Operator):
    bl_idname = "clip.error_value"
    bl_label = "Error Value"
    bl_description = "Berechnet die Standardabweichung der Markerpositionen der Selektion"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        x_positions = []
        y_positions = []

        for track in clip.tracking.tracks:
            if not track.select:
                continue
            for marker in track.markers:
                if marker.mute:
                    continue
                x_positions.append(marker.co[0])
                y_positions.append(marker.co[1])

        if not x_positions:
            self.report({'WARNING'}, "Keine Marker ausgewählt")
            return {'CANCELLED'}

        error_x = std_dev(x_positions)
        error_y = std_dev(y_positions)
        total_error = error_x + error_y

        self.report({'INFO'}, f"Error X: {error_x:.4f}, Error Y: {error_y:.4f}, Total: {total_error:.4f}")
        print(f"[Error Value] error_x={error_x:.6f}, error_y={error_y:.6f}, total={total_error:.6f}")

        return {'FINISHED'}


# Hilfsfunktion für Standardabweichung
def std_dev(values):
    mean_val = sum(values) / len(values)
    return (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5


# Funktion für internes Scoring (z. B. in optimize_tracking.py)
def error_value(scene):
    area = next((a for a in bpy.context.window.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        return 0.0
    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
    clip = space.clip if space else None
    if not clip:
        return 0.0

    x_positions = []
    y_positions = []

    for track in clip.tracking.tracks:
        if not track.select:
            continue
        for marker in track.markers:
            if marker.mute:
                continue
            x_positions.append(marker.co[0])
            y_positions.append(marker.co[1])

    if not x_positions:
        return 0.0

    return std_dev(x_positions) + std_dev(y_positions)


# Registrierung (optional, falls einzeln getestet wird)
def register():
    bpy.utils.register_class(CLIP_OT_error_value)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_error_value)

if __name__ == "__main__":
    register()

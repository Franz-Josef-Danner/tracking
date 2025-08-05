import bpy

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

        self.report(
            {'INFO'},
            f"Error X: {error_x:.4f}, Error Y: {error_y:.4f}, Total: {total_error:.4f}"
        )
        print(f"[Error Value] error_x={error_x:.6f}, error_y={error_y:.6f}, total={total_error:.6f}")
        return {'FINISHED'}


def std_dev(values):
    mean_val = sum(values) / len(values)
    return (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5


def calculate_clip_error(clip):
    """Berechnet die Gesamt-Standardabweichung (X + Y) für alle Marker im Clip."""
    x_pos = []
    y_pos = []

    for track in clip.tracking.tracks:
        for marker in track.markers:
            if marker.mute:
                continue
            x_pos.append(marker.co[0])
            y_pos.append(marker.co[1])

    if not x_pos:
        return 0.0

    return std_dev(x_pos) + std_dev(y_pos)


# Registrierung
def register():
    bpy.utils.register_class(CLIP_OT_error_value)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_error_value)

if __name__ == "__main__":
    register()

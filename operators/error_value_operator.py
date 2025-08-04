import bpy
from bpy.types import Operator


class CLIP_OT_error_value(Operator):
    bl_idname = "clip.error_value"
    bl_label = "Error Value"
    bl_description = "Berechnet die Standardabweichung der Markerpositionen der Selektion"

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "CLIP_EDITOR"
            and getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        x_positions = []
        y_positions = []

        tracking = clip.tracking
        tracks = tracking.objects.active.tracks

        for track in tracks:
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

        def std_dev(values):
            mean_val = sum(values) / len(values)
            return (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5

        error_x = std_dev(x_positions)
        error_y = std_dev(y_positions)
        total_error = error_x + error_y

        self.report({'INFO'}, f"Error X: {error_x:.4f} | Error Y: {error_y:.4f} | Gesamt: {total_error:.4f}")
        print(f"[Error Value] error_x={error_x:.6f}, error_y={error_y:.6f}, total={total_error:.6f}")

        return {'FINISHED'}


# Alias for backward compatibility
error_value = CLIP_OT_error_value

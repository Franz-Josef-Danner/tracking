# operators/reset_thresholds.py
import bpy

class KAISERLICH_OT_reset_thresholds(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.auto_calibrate"
    bl_label  = "Thresholds → 1"
    bl_options = {'REGISTER', 'UNDO'}

    _TARGETS = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )

    def execute(self, context):
        s = context.scene
        missing = []
        for attr in self._TARGETS:
            if hasattr(s, attr):
                setattr(s, attr, 1.0)
            else:
                missing.append(attr)

        if missing:
            self.report({'WARNING'}, "Nicht gefunden: " + ", ".join(missing))
        self.report({'INFO'}, "Alle Thresholds auf 1 gesetzt.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(KAISERLICH_OT_reset_thresholds)

def unregister():
    bpy.utils.unregister_class(KAISERLICH_OT_reset_thresholds)

bl_info = {
    "name": "Refine Markers Button",
    "blender": (2, 80, 0),
    "category": "Clip",
    "author": "Blender Lehrer",
    "description": "Fügt einen Button hinzu, um Marker im aktuellen Frame zu verfeinern."
}

import bpy

class CLIP_OT_refine_selected_markers(bpy.types.Operator):
    bl_idname = "clip.refine_selected_markers"
    bl_label = "Refine Selected Markers"
    bl_description = "Refine Tracking (vorwärts und rückwärts) für Marker im aktuellen Frame"

    def execute(self, context):
        space = context.space_data
        clip = space.clip
        frame_current = context.scene.frame_current

        if not clip:
            self.report({'WARNING'}, "Kein Movie Clip geladen.")
            return {'CANCELLED'}

        # Marker im aktuellen Frame selektieren
        for track in clip.tracking.tracks:
            marker = track.markers.find_frame(frame_current)
            track.select = marker is not None and not marker.mute

        # Rückwärts Refine
        bpy.ops.clip.refine_markers(backwards=True)
        # Vorwärts Refine
        bpy.ops.clip.refine_markers(backwards=False)

        self.report({'INFO'}, "Refine abgeschlossen.")
        return {'FINISHED'}

classes = (CLIP_OT_refine_selected_markers,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

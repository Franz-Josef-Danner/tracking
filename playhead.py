bl_info = {
    "name": "Jump to Sparse Marker Frame",
    "author": "Blender Lehrer",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "Clip Editor > Sidebar > Marker Tools",
    "description": "Setzt den Playhead auf den ersten Frame mit weniger als 10 Markern",
    "category": "Clip Editor",
}

import bpy

# Die Operator-Klasse
class CLIP_OT_jump_to_sparse_marker_frame(bpy.types.Operator):
    bl_idname = "clip.jump_to_sparse_marker"
    bl_label = "Jump to Sparse Marker Frame"
    bl_description = "Springt zum ersten Frame mit weniger als 10 Markern"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.IntProperty(
        name="Marker-Schwelle",
        description="Maximale Anzahl Marker pro Frame",
        default=10,
        min=1,
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not clip.tracking.tracks:
            self.report({'WARNING'}, "Keine Tracking-Daten vorhanden")
            return {'CANCELLED'}

        # Zähle Marker pro Frame
        frame_marker_count = {}
        for track in clip.tracking.tracks:
            for marker in track.markers:
                if not marker.mute:
                    frame = marker.frame
                    frame_marker_count[frame] = frame_marker_count.get(frame, 0) + 1

        start = scene.frame_start
        end = scene.frame_end

        for frame in range(start, end + 1):
            count = frame_marker_count.get(frame, 0)
            if count < self.threshold:
                scene.frame_current = frame
                self.report({'INFO'}, f"Gesprungen zu Frame {frame} mit {count} Marker(n)")
                return {'FINISHED'}

        self.report({'INFO'}, f"Kein Frame mit weniger als {self.threshold} Markern gefunden.")
        return {'CANCELLED'}


# UI-Panel in der Sidebar des Clip Editors
# Registrierung
classes = (CLIP_OT_jump_to_sparse_marker_frame,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

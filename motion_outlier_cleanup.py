bl_info = {
    "name": "Motion Outlier Cleanup",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "category": "Clip",
    "description": "L\u00f6scht Marker, deren Bewegung stark vom Durchschnitt abweicht.",
}

import bpy


class CLIP_OT_remove_motion_outliers(bpy.types.Operator):
    bl_idname = "clip.remove_motion_outliers"
    bl_label = "Motion Outlier Cleanup"
    bl_description = "Entfernt Marker mit starker Bewegungsabweichung"
    bl_options = {"REGISTER", "UNDO"}

    threshold: bpy.props.FloatProperty(
        name="Abweichungs-Schwelle",
        default=0.2,
        min=0.0,
        description="Tolerierte Abweichung von der mittleren Bewegung",
    )

    @classmethod
    def poll(cls, context):
        return (
            context.space_data
            and context.space_data.type == 'CLIP_EDITOR'
            and context.space_data.clip
        )

    def cleanup_frame(self, context, clip, frame):
        tracks = clip.tracking.tracks
        values = []
        valid_tracks = []

        for track in tracks:
            prev_marker = track.markers.find_frame(frame - 1)
            curr_marker = track.markers.find_frame(frame)
            next_marker = track.markers.find_frame(frame + 1)

            if not (prev_marker and curr_marker and next_marker):
                continue
            if prev_marker.mute or curr_marker.mute or next_marker.mute:
                continue

            xf1, yf1 = prev_marker.co
            xf2, yf2 = curr_marker.co
            xf3, yf3 = next_marker.co

            tx = (xf2 - xf1) + (xf3 - xf2)
            ty = (yf2 - yf1) + (yf3 - yf2)

            values.append((tx, ty))
            valid_tracks.append(track)

        if not values:
            return 0

        txg = sum(v[0] for v in values) / len(values)
        tyg = sum(v[1] for v in values) / len(values)

        to_delete = [
            track
            for track, (tx, ty) in zip(valid_tracks, values)
            if abs(tx - txg) > self.threshold or abs(ty - tyg) > self.threshold
        ]

        if not to_delete:
            return 0

        for t in tracks:
            t.select = False
        for t in to_delete:
            t.select = True

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'CLIP_EDITOR':
                                with context.temp_override(
                                    area=area,
                                    region=region,
                                    space_data=space,
                                ):
                                    bpy.ops.clip.delete_track()
                                return len(to_delete)

        return 0

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip

        start = scene.frame_start
        end = scene.frame_end
        scene.frame_current = start + 1

        total_deleted = 0
        for frame in range(start + 1, end):
            scene.frame_current = frame
            total_deleted += self.cleanup_frame(context, clip, frame)

        self.report({'INFO'}, f"Gesamt gelöscht: {total_deleted} Marker")
        return {'FINISHED'}


class CLIP_PT_motion_outlier_panel(bpy.types.Panel):
    bl_label = "Motion Cleanup"
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tools'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.window_manager, "outlier_threshold")
        op = layout.operator(CLIP_OT_remove_motion_outliers.bl_idname)
        op.threshold = context.window_manager.outlier_threshold


classes = (
    CLIP_OT_remove_motion_outliers,
    CLIP_PT_motion_outlier_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.WindowManager, "outlier_threshold"):
        bpy.types.WindowManager.outlier_threshold = bpy.props.FloatProperty(
            name="Abweichungs-Schwelle",
            default=0.2,
            min=0.0,
            description="Tolerierte Abweichung von der mittleren Bewegung",
        )


def unregister():
    if hasattr(bpy.types.WindowManager, "outlier_threshold"):
        del bpy.types.WindowManager.outlier_threshold
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()

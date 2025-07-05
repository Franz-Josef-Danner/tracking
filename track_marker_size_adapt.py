import bpy


def track_selected_markers_one_frame():
    """Track selected markers forward by one frame and print positions."""
    ctx = bpy.context
    area = ctx.area
    if not area or area.type != 'CLIP_EDITOR':
        print("track_one_frame: ❌ Kein Movie Clip Editor aktiv")
        return

    space = area.spaces.active
    clip = space.clip
    if not clip:
        print("track_one_frame: ❌ Kein Clip geladen")
        return

    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("track_one_frame: ❌ Kein Marker ausgewählt")
        return

    scene = ctx.scene
    frame = scene.frame_current

    print(f"track_one_frame: Start bei Frame {frame}")
    for t in tracks:
        marker = next((m for m in t.markers if m.frame == frame), None)
        if marker:
            print(f"  {t.name}: Start ({marker.co.x:.4f}, {marker.co.y:.4f})")
        else:
            print(f"  {t.name}: kein Marker auf Frame {frame}")

    result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
    print(f"track_markers result: {result}")

    next_frame = frame + 1
    for t in tracks:
        marker = next((m for m in t.markers if m.frame == next_frame), None)
        if marker:
            print(f"  {t.name}: Nachher ({marker.co.x:.4f}, {marker.co.y:.4f})")
        else:
            print(f"  {t.name}: kein Marker auf Frame {next_frame}")

    scene.frame_set(next_frame)


class TRACKING_OT_track_one_frame(bpy.types.Operator):
    bl_idname = "tracking.track_one_frame"
    bl_label = "Track One Frame"
    bl_description = "Trackt ausgewählte Marker um ein Frame vorwärts"

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'CLIP_EDITOR' and area.spaces.active.clip

    def execute(self, context):
        track_selected_markers_one_frame()
        return {'FINISHED'}


class TRACKING_PT_track_one_frame(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Track One Frame'

    def draw(self, context):
        self.layout.operator(TRACKING_OT_track_one_frame.bl_idname, icon='TRACKING_FORWARDS')


classes = [TRACKING_OT_track_one_frame, TRACKING_PT_track_one_frame]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

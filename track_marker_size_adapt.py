import bpy


def track_selected_markers_until_stop():
    """Track selected markers frame by frame until none remain active."""
    ctx = bpy.context
    area = ctx.area
    if not area or area.type != 'CLIP_EDITOR':
        print("track_until_stop: ❌ Kein Movie Clip Editor aktiv")
        return

    space = area.spaces.active
    clip = space.clip
    if not clip:
        print("track_until_stop: ❌ Kein Clip geladen")
        return

    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("track_until_stop: ❌ Kein Marker ausgewählt")
        return

    scene = ctx.scene
    start_frame = scene.frame_current

    active_tracks = tracks[:]
    iteration = 0
    while active_tracks:
        iteration += 1
        frame = scene.frame_current
        print(f"track_until_stop: Iteration {iteration} bei Frame {frame}")

        result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
        print(f"track_markers result: {result}")

        next_frame = frame + 1
        survivors = []
        for t in active_tracks:
            if t.markers.find_frame(next_frame):
                survivors.append(t)
            else:
                print(f"  {t.name}: kein Marker auf Frame {next_frame} -> entfernt")

        active_tracks = survivors
        if active_tracks:
            scene.frame_set(next_frame)

    scene.frame_set(start_frame)
    print("track_until_stop: ⭐ Tracking beendet")


class TRACKING_OT_track_until_stop(bpy.types.Operator):
    bl_idname = "tracking.track_until_stop"
    bl_label = "Track Until Stop"
    bl_description = "Trackt ausgewählte Marker frameweise bis keiner mehr aktiv ist"

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'CLIP_EDITOR' and area.spaces.active.clip

    def execute(self, context):
        track_selected_markers_until_stop()
        return {'FINISHED'}


class TRACKING_PT_track_until_stop(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Track Until Stop'

    def draw(self, context):
        self.layout.operator(TRACKING_OT_track_until_stop.bl_idname, icon='TRACKING_FORWARDS')


classes = [TRACKING_OT_track_until_stop, TRACKING_PT_track_until_stop]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

import bpy


def track_selected_markers_one_frame():
    """Track all selected markers for a single frame and print their positions."""
    ctx = bpy.context
    area = ctx.area
    if not area or area.type != 'CLIP_EDITOR':
        print("tracking.track_one_frame: ❌ Kein Movie Clip Editor aktiv")
        return
    space = area.spaces.active
    clip = space.clip
    if not clip:
        print("tracking.track_one_frame: ❌ Kein Clip geladen")
        return
    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("tracking.track_one_frame: ❌ Kein Marker ausgewählt")
        return

    scene = ctx.scene
    frame = scene.frame_current

    start_pos = {}
    for t in tracks:
        marker = next((m for m in t.markers if m.frame == frame), None)
        if marker:
            start_pos[t.as_pointer()] = marker.co.copy()
            print(f"Vorher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})")
        else:
            print(f"Vorher {t.name}: kein Marker auf Frame {frame}")

    bpy.ops.clip.track_markers(backwards=False, sequence=False)

    next_frame = frame + 1
    for t in tracks:
        marker = next((m for m in t.markers if m.frame == next_frame), None)
        if marker:
            print(f"Nachher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})")
            start = start_pos.get(t.as_pointer())
            if start is not None:
                dx = marker.co.x - start.x
                dy = marker.co.y - start.y
                print(f"Differenz {t.name}: ({dx:.4f}, {dy:.4f})")
        else:
            print(f"Nachher {t.name}: kein Marker auf Frame {next_frame}")

    print("tracking.track_one_frame: ✅ Frame getrackt")


class TRACKING_OT_track_one_frame(bpy.types.Operator):
    bl_idname = "tracking.track_one_frame"
    bl_label = "Track One Frame"
    bl_description = "Trackt ausgewählte Marker nur einen Frame lang"

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
        self.layout.operator(TRACKING_OT_track_one_frame.bl_idname, icon='TRACKING')


classes = [TRACKING_OT_track_one_frame, TRACKING_PT_track_one_frame]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

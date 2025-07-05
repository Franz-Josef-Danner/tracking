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

    def _get_corners(marker):
        """Return pattern corners as four (x, y) pairs."""
        c = marker.pattern_corners
        if len(c) == 8 and not isinstance(c[0], (list, tuple)):
            return [(float(c[i]), float(c[i + 1])) for i in range(0, 8, 2)]
        return [(float(x), float(y)) for x, y in c]

    start_data = {}

    for t in tracks:
        marker = next((m for m in t.markers if m.frame == frame), None)
        if marker:
            start_data[t.as_pointer()] = {
                'co': marker.co.copy(),
                'corners': _get_corners(marker),
            }
            print(f"Vorher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})")
        else:
            print(f"Vorher {t.name}: kein Marker auf Frame {frame}")

    bpy.ops.clip.track_markers(backwards=False, sequence=False)

    next_frame = frame + 1
    for t in tracks:
        marker = next((m for m in t.markers if m.frame == next_frame), None)
        start = start_data.get(t.as_pointer())
        if marker:
            print(f"Nachher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})")
            if start is not None:
                dx = marker.co.x - start['co'].x
                dy = marker.co.y - start['co'].y
                dist = (dx * dx + dy * dy) ** 0.5

                before = start['corners']
                after = _get_corners(marker)

                d0_before = (
                    before[2][0] - before[0][0],
                    before[2][1] - before[0][1],
                )
                d0_after = (
                    after[2][0] - after[0][0],
                    after[2][1] - after[0][1],
                )
                d1_before = (
                    before[3][0] - before[1][0],
                    before[3][1] - before[1][1],
                )
                d1_after = (
                    after[3][0] - after[1][0],
                    after[3][1] - after[1][1],
                )

                diff0 = (
                    d0_after[0] - d0_before[0],
                    d0_after[1] - d0_before[1],
                )
                diff1 = (
                    d1_after[0] - d1_before[0],
                    d1_after[1] - d1_before[1],
                )

                print(
                    f"Differenz {t.name}: ({dx:.4f}, {dy:.4f}), Distanz {dist:.4f}"
                )
                print(
                    f"Eck-Deltas {t.name}: diag0 ({diff0[0]:.4f}, {diff0[1]:.4f}),"
                    f" diag1 ({diff1[0]:.4f}, {diff1[1]:.4f})"
                )
        else:
            print(f"Nachher {t.name}: kein Marker auf Frame {next_frame}")
            if start is not None:
                print(f"Differenz {t.name}: nicht ermittelbar")

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

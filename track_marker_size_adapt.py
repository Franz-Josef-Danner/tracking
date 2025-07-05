import bpy


def track_selected_markers_until_stop():
    """Track selected markers frame by frame until none remain active."""
    ctx = bpy.context
    area = ctx.area
    if not area or area.type != 'CLIP_EDITOR':
        print("tracking.track_until_stop: ❌ Kein Movie Clip Editor aktiv")
        return
    space = area.spaces.active
    clip = space.clip
    if not clip:
        print("tracking.track_until_stop: ❌ Kein Clip geladen")
        return
    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("tracking.track_until_stop: ❌ Kein Marker ausgewählt")
        return

    scene = ctx.scene
    frame = scene.frame_current

    def _get_corners(marker):
        c = marker.pattern_corners
        if len(c) == 8 and not isinstance(c[0], (list, tuple)):
            return [(float(c[i]), float(c[i + 1])) for i in range(0, 8, 2)]
        return [(float(x), float(y)) for x, y in c]

    def _set_corners(marker, corners):
        marker.pattern_corners = [(float(x), float(y)) for x, y in corners]

    while tracks:
        start_pos = {}
        for t in tracks:
            marker = next((m for m in t.markers if m.frame == frame), None)
            start_pos[t.as_pointer()] = marker.co.copy() if marker else None

        results = []

        bpy.ops.clip.track_markers(backwards=False, sequence=False)

        next_frame = frame + 1
        for t in tracks[:]:
            marker = next((m for m in t.markers if m.frame == next_frame), None)
            start_co = start_pos.get(t.as_pointer())
            if not marker:
                tracks.remove(t)
                results.append([
                    f"Start {t.name}: kein Marker auf Frame {frame}",
                    f"Nachher {t.name}: kein Marker auf Frame {next_frame}",
                ])
                continue

            after_corners = _get_corners(marker)
            d0_len = (
                (after_corners[2][0] - after_corners[0][0]) ** 2
                + (after_corners[2][1] - after_corners[0][1]) ** 2
            ) ** 0.5
            d1_len = (
                (after_corners[3][0] - after_corners[1][0]) ** 2
                + (after_corners[3][1] - after_corners[1][1]) ** 2
            ) ** 0.5

            if start_co is None:
                results.append(
                    [
                        f"Start {t.name}: kein Marker auf Frame {frame}",
                        f"Nachher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})",
                        f"Diagonale 0 {t.name}: {d0_len:.4f}, Diagonale 1 {t.name}: {d1_len:.4f}",
                        f"Bewegung {t.name}: nicht ermittelbar",
                    ]
                )
                continue

            dx = marker.co.x - start_co.x
            dy = marker.co.y - start_co.y
            move_dist = (dx * dx + dy * dy) ** 0.5

            diff0 = move_dist - d0_len
            diff1 = move_dist - d1_len
            avg = (diff0 + diff1) / 2.0

            result_lines = [
                f"Start {t.name}: ({start_co.x:.4f}, {start_co.y:.4f})",
                f"Nachher {t.name}: ({marker.co.x:.4f}, {marker.co.y:.4f})",
                f"Diagonale 0 {t.name}: {d0_len:.4f}, Diagonale 1 {t.name}: {d1_len:.4f}",
                f"Bewegung {t.name}: {move_dist:.4f}, \u0394 zu Diag0 {diff0:.4f}, \u0394 zu Diag1 {diff1:.4f}, Mittel {avg:.4f}",
            ]

            pairs = [(0, 2), (1, 3)]
            for a, b in pairs:
                p1 = after_corners[a]
                p2 = after_corners[b]
                cx = (p1[0] + p2[0]) / 2.0
                cy = (p1[1] + p2[1]) / 2.0
                vx = p1[0] - cx
                vy = p1[1] - cy
                length = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
                if length:
                    scale = (length + avg) / length
                    vx *= scale
                    vy *= scale
                after_corners[a] = (cx + vx, cy + vy)
                after_corners[b] = (cx - vx, cy - vy)

            _set_corners(marker, after_corners)
            corner_info = ", ".join(f"({x:.4f}, {y:.4f})" for x, y in after_corners)
            result_lines.append(f"Ecken neu {t.name}: {corner_info}")
            results.append(result_lines)

        for lines in results:
            for line in lines:
                print(line)

        frame = next_frame
        scene.frame_set(frame)
        print("tracking.track_until_stop: ✅ Frame getrackt")

    print("tracking.track_until_stop: ⭐ Tracking beendet")


class TRACKING_OT_track_until_stop(bpy.types.Operator):
    bl_idname = "tracking.track_until_stop"
    bl_label = "Track Until Stop"
    bl_description = "Trackt ausgewählte Marker fortlaufend, bis keiner mehr aktiv ist"

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
        self.layout.operator(TRACKING_OT_track_until_stop.bl_idname, icon='TRACKING')


classes = [TRACKING_OT_track_until_stop, TRACKING_PT_track_until_stop]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

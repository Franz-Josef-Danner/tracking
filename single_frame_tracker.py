bl_info = {
    "name": "Single Frame Tracker",
    "blender": (2, 80, 0),
    "category": "Clip",
    "description": "Track selected markers frame by frame until none remain",
}

import bpy
from mathutils import Vector


def _resize_pattern(
    marker: bpy.types.MovieTrackingMarker, delta: Vector, clip: bpy.types.MovieClip
) -> None:
    """Resize the marker's pattern box based on translation delta."""
    corners = getattr(marker, "pattern_corners", None)
    if not corners or len(corners) < 8:
        return

    xs = [corners[i] for i in range(0, 8, 2)]
    ys = [corners[i] for i in range(1, 8, 2)]
    cx = sum(xs) / 4
    cy = sum(ys) / 4

    width_px = max(30.0, abs(delta.x) * clip.size[0])
    height_px = max(30.0, abs(delta.y) * clip.size[1])

    width = width_px / clip.size[0]
    height = height_px / clip.size[1]

    half_w = width / 2
    half_h = height / 2

    new_corners = [
        cx - half_w,
        cy - half_h,
        cx + half_w,
        cy - half_h,
        cx + half_w,
        cy + half_h,
        cx - half_w,
        cy + half_h,
    ]
    marker.pattern_corners = new_corners
    print(
        f"[Track Until Done] {marker.name} pattern resized to {width_px:.2f}x{height_px:.2f} px"
    )


def _marker_diagonal(marker: bpy.types.MovieTrackingMarker) -> tuple[float, float]:
    """Return the lengths of both diagonals of the marker's pattern box."""
    corners = getattr(marker, "pattern_corners", None)
    if corners and len(corners) >= 8:
        x1, y1, x2, y2, x3, y3, x4, y4 = corners[:8]
        p1 = Vector(marker.co) + Vector((x1, y1))
        p2 = Vector(marker.co) + Vector((x2, y2))
        p3 = Vector(marker.co) + Vector((x3, y3))
        p4 = Vector(marker.co) + Vector((x4, y4))
        d1 = (p3 - p1).length
        d2 = (p4 - p2).length
        return d1, d2
    return 0.0, 0.0


def _pattern_size(marker: bpy.types.MovieTrackingMarker, clip: bpy.types.MovieClip) -> tuple[float, float] | None:
    """Return the pattern box size in pixels."""
    corners = getattr(marker, "pattern_corners", None)
    if corners and len(corners) >= 8:
        xs = [corners[i] for i in range(0, 8, 2)]
        ys = [corners[i] for i in range(1, 8, 2)]
        width_px = (max(xs) - min(xs)) * clip.size[0]
        height_px = (max(ys) - min(ys)) * clip.size[1]
        return width_px, height_px
    return None

class CLIP_OT_track_one_frame(bpy.types.Operator):
    """Track selected markers forward by one frame until they can't move further"""
    bl_idname = "clip.track_one_frame"
    bl_label = "Track Until Done"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene_end = context.scene.frame_end
        iterations = 0

        print("[Track Until Done] Starting frame-by-frame tracking...")

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = next((s for s in area.spaces if s.type == 'CLIP_EDITOR'), None)
                    if not space:
                        continue
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region, space_data=space):
                                clip = space.clip
                                if not clip:
                                    print("[Track Until Done] No clip loaded.")
                                    continue

                                clip_user = space.clip_user
                                frame = clip_user.frame_current
                                bpy.context.scene.frame_set(frame)
                                clip_user.frame_current = frame

                                prev_positions = {}
                                prev_diagonals = {}
                                while frame <= scene_end:
                                    # Some Blender versions don't define the
                                    # 'mute' attribute. Use getattr() so the
                                    # check works everywhere.
                                    active_tracks = [
                                        t
                                        for t in clip.tracking.tracks
                                        if t.select and not getattr(t, "mute", False)
                                    ]
                                    if not active_tracks:
                                        print(f"[Track Until Done] No active markers left at frame {frame}.")
                                        break

                                    print(
                                        f"[Track Until Done] Frame {frame} (clip {clip_user.frame_current}), active markers: {len(active_tracks)}"
                                    )
                                    for t in active_tracks:
                                        marker_or_index = t.markers.find_frame(frame)
                                        if marker_or_index != -1 and marker_or_index is not None:
                                            if isinstance(marker_or_index, int):
                                                marker = t.markers[marker_or_index]
                                            else:
                                                marker = marker_or_index
                                            prev_positions[t.name] = Vector(marker.co)
                                            prev_diagonals[t.name] = _marker_diagonal(marker)
                                    result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
                                    print(f"[Track Until Done] Result: {result}")

                                    if 'CANCELLED' in result:
                                        print(f"[Track Until Done] Tracking cancelled at frame {frame}.")
                                        break

                                    distances = []
                                    scales = []
                                    for t in active_tracks:
                                        prev = prev_positions.get(t.name)
                                        next_marker_or_index = t.markers.find_frame(frame + 1)
                                        if prev is not None and next_marker_or_index != -1 and next_marker_or_index is not None:
                                            if isinstance(next_marker_or_index, int):
                                                next_marker = t.markers[next_marker_or_index]
                                            else:
                                                next_marker = next_marker_or_index
                                            dist = (Vector(next_marker.co) - prev).length
                                            distances.append(f"{t.name}: {dist:.4f}")
                                            _resize_pattern(
                                                next_marker,
                                                Vector(next_marker.co) - prev,
                                                clip,
                                            )
                                            size_px = _pattern_size(next_marker, clip)
                                            if size_px:
                                                print(
                                                    f"[Track Until Done] {t.name} pattern size {size_px[0]:.2f}x{size_px[1]:.2f} px"
                                                )
                                            prev_positions[t.name] = Vector(next_marker.co)
                                            old_d1, old_d2 = prev_diagonals.get(t.name, (0.0, 0.0))
                                            new_d1, new_d2 = _marker_diagonal(next_marker)
                                            if old_d1 and old_d2:
                                                scale1 = new_d1 / old_d1
                                                scale2 = new_d2 / old_d2
                                                scales.append(f"{t.name}: {scale1:.4f}, {scale2:.4f}")
                                            prev_diagonals[t.name] = (new_d1, new_d2)
                                    if distances:
                                        print("[Track Until Done] Distances:", ", ".join(distances))
                                    if scales:
                                        print("[Track Until Done] Pattern Scales:", ", ".join(scales))

                                    frame += 1
                                    if frame > scene_end:
                                        print(
                                            f"[Track Until Done] Reached scene end frame {scene_end}."
                                        )
                                        break

                                    bpy.context.scene.frame_set(frame)
                                    clip_user.frame_current = frame
                                    iterations += 1

                                print(f"[Track Until Done] Finished at frame {frame} after {iterations} steps.")
                                self.report({'INFO'}, f"Tracking completed in {iterations} steps.")
                                return {'FINISHED'}

        print("[Track Until Done] No Clip Editor found.")
        self.report({'WARNING'}, "No suitable Clip Editor context found.")
        return {'CANCELLED'}


class CLIP_PT_one_frame_tracker_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Tracking"
    bl_label = "One Frame Tracker"

    def draw(self, context):
        layout = self.layout
        layout.operator("clip.track_one_frame", text="Track Until Done")


def register():
    bpy.utils.register_class(CLIP_OT_track_one_frame)
    bpy.utils.register_class(CLIP_PT_one_frame_tracker_panel)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_track_one_frame)
    bpy.utils.unregister_class(CLIP_PT_one_frame_tracker_panel)


if __name__ == "__main__":
    register()

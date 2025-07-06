bl_info = {
    "name": "Single Frame Tracker",
    "blender": (2, 80, 0),
    "category": "Clip",
    "description": "Track selected markers frame by frame until none remain",
}

import bpy
from mathutils import Vector


def _marker_diagonal(
    track: bpy.types.MovieTrackingTrack, marker: bpy.types.MovieTrackingMarker
) -> tuple[float, float]:
    """Return both diagonals of the marker's pattern box."""
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
                                while frame <= scene_end:
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
                                    result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
                                    print(f"[Track Until Done] Result: {result}")

                                    if 'CANCELLED' in result:
                                        print(f"[Track Until Done] Tracking cancelled at frame {frame}.")
                                        break

                                    distances = []
                                    diagonals = []
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
                                            prev_positions[t.name] = Vector(next_marker.co)
                                            d1, d2 = _marker_diagonal(t, next_marker)
                                            diagonals.append(
                                                f"{t.name}: {d1:.4f}, {d2:.4f}"
                                            )
                                    if distances:
                                        print("[Track Until Done] Distances:", ", ".join(distances))
                                    if diagonals:
                                        print("[Track Until Done] Diagonals:", ", ".join(diagonals))

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

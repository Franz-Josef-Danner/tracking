import bpy
import math


def adapt_marker_size_from_tracks(context, operator=None):
    """Track and scale selected markers until none remain active.

    Parameters
    ----------
    context : bpy.types.Context
        Blender context used for overrides.
    operator : bpy.types.Operator, optional
        Operator for UI reporting. When provided, messages are also shown in
        Blender's status bar.
    """

    def _report(message):
        print(message)
        if operator is not None:
            operator.report({'INFO'}, message)

    area = context.area
    if not area or area.type != 'CLIP_EDITOR':
        _report("❌ Kein Movie Clip Editor aktiv")
        return

    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    space = area.spaces.active
    clip = space.clip

    if not clip or not region:
        _report("❌ Kein Clip geladen")
        return

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        _report("❌ Keine Tracks ausgewählt")
        return

    scene = context.scene
    start_frame = scene.frame_current
    width, height = clip.size

    with context.temp_override(area=area, region=region, space_data=space):
        while any(t.select for t in selected_tracks):
            prev_counts = {
                t.as_pointer(): len(t.markers)
                for t in selected_tracks
                if t.select
            }
            bpy.ops.clip.track_markers(sequence=False)

            for track in list(selected_tracks):
                if not track.select:
                    selected_tracks.remove(track)
                    continue

                prev_len = prev_counts.get(track.as_pointer())
                if prev_len is None or len(track.markers) <= prev_len:
                    selected_tracks.remove(track)
                    continue

                prev = track.markers[-2]
                curr = track.markers[-1]
                dx = (curr.co.x - prev.co.x) * width
                dy = (curr.co.y - prev.co.y) * height
                dist = math.hypot(dx, dy)
                factor = 1.0 + dist / max(width, height)

                corners = list(curr.pattern_corners)
                cx = sum(corners[0::2]) / 4.0
                cy = sum(corners[1::2]) / 4.0
                scaled = []
                for i in range(0, 8, 2):
                    scaled.append(cx + (corners[i] - cx) * factor)
                    scaled.append(cy + (corners[i + 1] - cy) * factor)
                curr.pattern_corners = scaled

    scene.frame_set(start_frame)
    _report("⭐ Tracking beendet")


class TRACKING_OT_adapt_marker_size(bpy.types.Operator):
    bl_idname = "tracking.adapt_marker_size"
    bl_label = "Scale Marker Pattern"
    bl_description = (
        "Trackt ausgewählte Marker Frame für Frame und skaliert ihre Muster, "
        "bis keine Marker mehr aktiv sind"
    )

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'CLIP_EDITOR' and area.spaces.active.clip

    def execute(self, context):
        adapt_marker_size_from_tracks(context, operator=self)
        return {'FINISHED'}


class TRACKING_PT_adapt_marker_size(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Adapt Marker Size'

    def draw(self, context):
        self.layout.operator("tracking.adapt_marker_size", icon='TRACKING')


classes = [TRACKING_OT_adapt_marker_size, TRACKING_PT_adapt_marker_size]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

import bpy
import math


def adapt_marker_size_from_tracks(context):
    """Track selected markers and adapt pattern/search size."""

    area = context.area
    if not area or area.type != 'CLIP_EDITOR':
        print("❌ Kein Movie Clip Editor aktiv")
        return

    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    space = area.spaces.active
    clip = space.clip

    if not clip or not region:
        print("❌ Kein Clip geladen")
        return

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        print("❌ Keine Tracks ausgewählt")
        return

    scene = context.scene
    start_frame = scene.frame_current

    # Track selected markers only one frame to measure movement
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.track_markers(sequence=False)

    width, height = clip.size
    total_scale = 0.0
    valid_tracks = 0

    for track in selected_tracks:
        markers = track.markers
        if len(markers) < 2:
            continue

        prev = markers[-2]
        curr = markers[-1]
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

        total_scale += factor
        valid_tracks += 1

    if valid_tracks:
        pz = clip.tracking.settings.default_pattern_size * (total_scale / valid_tracks)
    else:
        pz = clip.tracking.settings.default_pattern_size

    print(f"⭐ Berechnete Pattern-Größe: {pz:.1f}")

    # Reset playhead
    scene.frame_set(start_frame)

    settings = clip.tracking.settings
    settings.default_pattern_size = int(pz)
    settings.default_search_size = int(pz * 2)

    # Detect features and track with new pattern/search size
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.detect_features()
        bpy.ops.clip.track_markers(sequence=True)


class TRACKING_OT_adapt_marker_size(bpy.types.Operator):
    bl_idname = "tracking.adapt_marker_size"
    bl_label = "Adapt Marker Size"
    bl_description = "Analyse ausgew\xE4hlte Tracks und passt Pattern-Gr\xF6\xDFe an"

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'CLIP_EDITOR' and area.spaces.active.clip

    def execute(self, context):
        adapt_marker_size_from_tracks(context)
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

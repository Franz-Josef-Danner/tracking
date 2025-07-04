import bpy
import math


def adapt_marker_size_from_tracks():
    """Track selected markers and adapt pattern size for detection."""
    clip = None
    area = None
    region = None
    space = None
    for a in bpy.context.screen.areas:
        if a.type == 'CLIP_EDITOR':
            area = a
            space = a.spaces.active
            region = next((r for r in a.regions if r.type == 'WINDOW'), None)
            clip = space.clip
            break
    if not clip or not region:
        print("❌ Kein Movie Clip Editor aktiv")
        return

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        print("❌ Keine Tracks ausgewählt")
        return

    scene = bpy.context.scene
    start_frame = scene.frame_current

    with bpy.context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.track_markers(sequence=True)

    width, height = clip.size
    sum_dx = sum_dy = sum_ds = 0.0
    steps = 0

    for track in selected_tracks:
        markers = sorted(track.markers, key=lambda m: m.frame)
        for m_prev, m_cur in zip(markers, markers[1:]):
            sum_dx += abs(m_cur.co.x - m_prev.co.x) * width
            sum_dy += abs(m_cur.co.y - m_prev.co.y) * height
            sum_ds += abs(m_cur.pattern_width - m_prev.pattern_width)
            steps += 1

    ma = len(selected_tracks)
    if steps and ma:
        pz = ((sum_dx + sum_dy + sum_ds) / steps) / ma
    else:
        pz = clip.tracking.settings.default_pattern_size

    print(f"⭐ Berechnete Pattern-Größe: {pz:.1f}")

    scene.frame_set(start_frame)

    settings = clip.tracking.settings
    settings.default_pattern_size = int(pz)
    settings.default_search_size = int(pz * 2)

    with bpy.context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.detect_features()
        bpy.ops.clip.track_markers(sequence=True)


class TRACKING_OT_adapt_marker_size(bpy.types.Operator):
    bl_idname = "tracking.adapt_marker_size"
    bl_label = "Adapt Marker Size"

    def execute(self, context):
        adapt_marker_size_from_tracks()
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

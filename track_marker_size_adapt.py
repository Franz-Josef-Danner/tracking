import bpy
import math


def _pattern_scale(marker):
    """Return the average diagonal length of a marker's pattern corners."""
    c = list(marker.pattern_corners)
    # pattern_corners may be a flat list of 8 floats or 4 pairs
    if len(c) == 8:
        pts = [(c[i], c[i + 1]) for i in range(0, 8, 2)]
    else:
        pts = [tuple(p) for p in c]
    d1 = math.dist(pts[0], pts[2])
    d2 = math.dist(pts[1], pts[3])
    return (d1 + d2) / 2.0


def adapt_marker_size_from_tracks():
    """Track selected markers until none remain and compute new pattern size."""
    ctx = bpy.context
    area = ctx.area
    if not area or area.type != "CLIP_EDITOR":
        print("adapt_marker_size: ❌ Kein Movie Clip Editor aktiv")
        return

    clip = area.spaces.active.clip
    if not clip:
        print("adapt_marker_size: ❌ Kein Clip geladen")
        return

    tracks = [t for t in clip.tracking.tracks if t.select]
    if not tracks:
        print("adapt_marker_size: ❌ Kein Marker ausgewählt")
        return

    scene = ctx.scene
    start_frame = scene.frame_current

    # --- track until markers are gone ---
    active = tracks[:]
    iteration = 0
    while active:
        iteration += 1
        frame = scene.frame_current
        print(f"adapt_marker_size: Iteration {iteration} bei Frame {frame}")

        result = bpy.ops.clip.track_markers(backwards=False, sequence=False)
        print(f"track_markers result: {result}")

        next_f = frame + 1
        survivors = []
        for t in active:
            if t.markers.find_frame(next_f):
                survivors.append(t)
            else:
                print(f"  {t.name}: kein Marker auf Frame {next_f} -> entfernt")

        active = survivors
        if active:
            scene.frame_set(next_f)

    # --- gather information ---
    sum_x = sum_y = sum_scale = 0.0
    total_len = 0
    for t in tracks:
        if not t.markers:
            continue
        first = t.markers[0].frame
        last = t.markers[-1].frame
        total_len += last - first if last > first else 0
        m = t.markers[-1]
        sum_x += m.co.x
        sum_y += m.co.y
        sum_scale += _pattern_scale(m)

    ma = len(tracks)
    if total_len and ma:
        pz = ((sum_x + sum_y + sum_scale) / total_len) / ma
    else:
        pz = 0.0

    print(
        f"adapt_marker_size: Ma={ma}, sum_x={sum_x:.4f}, sum_y={sum_y:.4f}, "
        f"sum_scale={sum_scale:.4f}, total_len={total_len}, Pz={pz:.4f}"
    )

    # restore frame
    scene.frame_set(start_frame)

    # update defaults and retrack
    settings = clip.tracking.settings
    settings.default_pattern_size = pz
    settings.default_search_size = pz * 2
    print(
        f"adapt_marker_size: pattern_size={settings.default_pattern_size:.4f}, "
        f"search_size={settings.default_search_size:.4f}"
    )

    bpy.ops.clip.detect_features()
    bpy.ops.clip.track_markers(backwards=False, sequence=False)
    print("adapt_marker_size: ⭐ Fertig")


class TRACKING_OT_adapt_marker_size(bpy.types.Operator):
    bl_idname = "tracking.adapt_marker_size"
    bl_label = "Adapt Marker Size"
    bl_description = "Trackt ausgewählte Marker bis zum Ende und passt Standard-Gr\xF6\xDFen an"

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'CLIP_EDITOR' and area.spaces.active.clip

    def execute(self, context):
        adapt_marker_size_from_tracks()
        return {'FINISHED'}


class TRACKING_PT_adapt_marker_size(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Adapt Marker Size'

    def draw(self, context):
        self.layout.operator(TRACKING_OT_adapt_marker_size.bl_idname, icon='TRACKING_FORWARDS')


classes = [TRACKING_OT_adapt_marker_size, TRACKING_PT_adapt_marker_size]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

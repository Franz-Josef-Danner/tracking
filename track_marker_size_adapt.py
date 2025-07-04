import bpy


def marker_size_adapt():
    """Track selected markers and adjust pattern/search size."""

    clip = None
    for area in bpy.context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            clip = area.spaces.active.clip
            break
    if not clip:
        print("❌ Kein Movie Clip Editor aktiv")
        return

    scene = bpy.context.scene
    start = clip.frame_start

    selected_tracks = [t for t in clip.tracking.tracks if t.select]
    if not selected_tracks:
        print("❌ Keine selektierten Marker")
        return

    # Track all selected markers forward until none remain active
    scene.frame_set(start)
    bpy.ops.clip.track_markers(sequence=True)

    values = []
    for track in selected_tracks:
        if not track.markers:
            continue
        Ml = len(track.markers)
        last = track.markers[-1]
        mpx = last.co.x
        mpy = last.co.y
        msx = last.pattern_width
        msy = last.pattern_height
        values.append(((mpx + mpy + msx + msy) / 4.0) / Ml)

    if not values:
        print("❌ Keine Markerinformationen gefunden")
        return

    Ma = len(values)
    Pz = sum(values) / Ma

    print(f"🔧 Berechnete Patterngröße: {Pz:.3f}")

    # Reset playhead to start frame
    scene.frame_set(start)

    # Apply pattern and search size
    settings = clip.tracking.settings
    settings.default_pattern_size = Pz
    settings.default_search_size = Pz * 2

    # Detect new features with the updated sizes
    bpy.ops.clip.detect_features()

    # Track the newly detected markers
    bpy.ops.clip.track_markers(sequence=True)


class TRACKING_PT_marker_size_adapt(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Tracking'
    bl_label = 'Marker Size Adapt'

    def draw(self, context):
        self.layout.operator("tracking.marker_size_adapt", icon='TRACKING')


class TRACKING_OT_marker_size_adapt(bpy.types.Operator):
    bl_idname = "tracking.marker_size_adapt"
    bl_label = "Marker Size Adapt"

    def execute(self, context):
        marker_size_adapt()
        return {'FINISHED'}


classes = [
    TRACKING_PT_marker_size_adapt,
    TRACKING_OT_marker_size_adapt,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

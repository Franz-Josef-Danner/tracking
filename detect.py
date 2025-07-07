import bpy
import mathutils


def remove_close_new_tracks(context, clip, new_tracks, min_distance=0.02):
    """Delete newly detected tracks too close to existing GOOD_ tracks."""

    current_frame = context.scene.frame_current
    good_tracks = [t for t in clip.tracking.tracks if t.name.startswith("GOOD_")]

    if not good_tracks or not new_tracks:
        return 0

    to_remove = []
    for neu in new_tracks:
        neu_marker = neu.markers.find_frame(current_frame)
        if not neu_marker:
            continue
        neu_pos = mathutils.Vector(neu_marker.co)

        for good in good_tracks:
            good_marker = good.markers.find_frame(current_frame)
            if not good_marker:
                continue
            good_pos = mathutils.Vector(good_marker.co)

            if (neu_pos - good_pos).length < min_distance:
                to_remove.append(neu)
                break

    if not to_remove:
        return 0

    for t in clip.tracking.tracks:
        t.select = False
    for t in to_remove:
        t.select = True

    area = next((a for a in context.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if area:
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        space = area.spaces.active
        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.delete_track()

    return len(to_remove)

# Operator-Klasse
class DetectFeaturesCustomOperator(bpy.types.Operator):
    bl_idname = "clip.detect_features_custom"
    bl_label = "Detect Features (Custom)"

    def execute(self, context):
        """Run feature detection and lower threshold if none are found."""

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        threshold = 0.01
        min_new = context.scene.min_marker_count
        tracks_before = len(clip.tracking.tracks)

        print(
            f"[Detect] Running detection for {min_new} markers at "
            f"threshold {threshold:.4f}"
        )
        initial_names = {t.name for t in clip.tracking.tracks}
        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=500,
            min_distance=10,
            placement='FRAME',
        )

        new_tracks = [
            t for t in clip.tracking.tracks if t.name not in initial_names
        ]
        remove_close_new_tracks(context, clip, new_tracks)

        tracks_after = len(clip.tracking.tracks)

        while (tracks_after - tracks_before) < min_new and threshold > 0.0001:
            factor = ((tracks_after - tracks_before) + 0.1) / min_new
            threshold = max(threshold * factor, 0.0001)
            msg = (
                f"Nur {tracks_after - tracks_before} Features, "
                f"senke Threshold auf {threshold:.4f}"
            )
            print(f"[Detect] {msg}")
            self.report({'INFO'}, msg)
            initial_names = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=500,
                min_distance=10,
                placement='FRAME',
            )
            new_tracks = [
                t for t in clip.tracking.tracks if t.name not in initial_names
            ]
            remove_close_new_tracks(context, clip, new_tracks)
            tracks_after = len(clip.tracking.tracks)
        print(
            f"[Detect] Finished with {tracks_after - tracks_before} new markers"
        )
        return {'FINISHED'}

# Panel-Klasse
class CLIP_PT_DetectFeaturesPanel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Motion Tracking'
    bl_label = "Detect Features Tool"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "min_marker_count")
        layout.operator("clip.detect_features_custom", icon='VIEWZOOM')

# Registrierung
def register():
    bpy.types.Scene.min_marker_count = bpy.props.IntProperty(
        name="Min Marker Count",
        default=5,
        min=5,
        max=50,
        description="Minimum markers to detect each run",
    )

    bpy.utils.register_class(DetectFeaturesCustomOperator)
    bpy.utils.register_class(CLIP_PT_DetectFeaturesPanel)

def unregister():
    bpy.utils.unregister_class(DetectFeaturesCustomOperator)
    bpy.utils.unregister_class(CLIP_PT_DetectFeaturesPanel)

    del bpy.types.Scene.min_marker_count

if __name__ == "__main__":
    register()

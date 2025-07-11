import bpy
from margin_a_distanz import compute_margin_distance
# ``ensure_margin_distance`` moved to ``margin_distance_adapt`` after module rename
from margin_distance_adapt import ensure_margin_distance
from adjust_marker_count_plus import adjust_marker_count_plus
from count_new_markers import count_new_markers


def rename_new_tracks(clip, start_index, prefix="NEW_"):
    """Prefix newly created tracks with ``prefix``."""
    for track in list(clip.tracking.tracks)[start_index:]:
        if not track.name.startswith(prefix):
            track.name = f"{prefix}{track.name}"

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

        threshold = 0.1
        base_plus = context.scene.min_marker_count_plus
        min_new = context.scene.min_marker_count
        tracks_before = len(clip.tracking.tracks)
        settings = clip.tracking.settings
        settings.default_pattern_size = 50
        settings.default_search_size = settings.default_pattern_size * 2

        # Werte aus margin_a_distanz verwenden und an Threshold anpassen
        compute_margin_distance()
        margin, distance, _ = ensure_margin_distance(clip, threshold)

        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=margin,
            min_distance=distance,
            placement='FRAME',
        )
        rename_new_tracks(clip, tracks_before)

        tracks_after = len(clip.tracking.tracks)
        if tracks_after == tracks_before:
            settings.default_pattern_size = max(
                1,
                int(settings.default_pattern_size / 1.1),
            )
            settings.default_search_size = settings.default_pattern_size * 2

        new_marker = count_new_markers(clip)

        while new_marker < min_new and threshold > 0.0001:
            if tracks_after == tracks_before:
                settings.default_pattern_size = max(
                    1,
                    int(settings.default_pattern_size / 1.1),
                )
                settings.default_search_size = settings.default_pattern_size * 2

            adjust_marker_count_plus(context.scene, new_marker)
            base_plus = context.scene.min_marker_count_plus
            factor = (new_marker + 0.1) / base_plus
            threshold = max(threshold * factor, 0.0001)

            margin, distance, _ = ensure_margin_distance(clip, threshold)

            # vorhandene NEW_-Marker entfernen
            for track in list(clip.tracking.tracks):
                if track.name.startswith("NEW_"):
                    clip.tracking.tracks.remove(track)

            msg = (
                f"Nur {new_marker} Features, "
                f"senke Threshold auf {threshold:.4f}"
            )
            self.report({'INFO'}, msg)
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
                placement='FRAME',
            )
            rename_new_tracks(clip, tracks_before)
            tracks_after = len(clip.tracking.tracks)
            new_marker = count_new_markers(clip)
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

classes = (
    DetectFeaturesCustomOperator,
    CLIP_PT_DetectFeaturesPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)



def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

import bpy
import logging
from margin_utils import compute_margin_distance, ensure_margin_distance
from adjust_marker_count_plus import adjust_marker_count_plus

# Clamp pattern sizes to a sane range
PATTERN_SIZE_START = 50
PATTERN_SIZE_MAX = 100

logger = logging.getLogger(__name__)

# Operator-Klasse
class DetectFeaturesCustomOperator(bpy.types.Operator):
    bl_idname = "clip.detect_features_custom"
    bl_label = "Detect Features (Custom)"

    def execute(self, context):
        """Run feature detection and lower threshold if none are found.

        The operator may run from a timer or other context without
        ``space_data``. In that case use the scene's active clip.
        """

        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
        if clip is None:
            clip = getattr(context.scene, "clip", None)

        if not clip:
            self.report({'WARNING'}, "Kein Clip gefunden")
            return {'CANCELLED'}

        # Proxy vor der Erkennung ausschalten
        if clip.use_proxy:
            logger.info("Proxy für Detection deaktivieren")
            clip.use_proxy = False
            print("Proxy deaktiviert")

        threshold = 1.0
        base_plus = context.scene.min_marker_count_plus
        min_new = context.scene.min_marker_count
        base_count = len(clip.tracking.tracks)
        settings = clip.tracking.settings
        settings.default_pattern_size = min(PATTERN_SIZE_START, PATTERN_SIZE_MAX)
        settings.default_search_size = settings.default_pattern_size * 2

        # Werte aus margin_utils verwenden und an Threshold anpassen
        compute_margin_distance()
        margin, distance, _ = ensure_margin_distance(clip, threshold)

        bpy.ops.clip.detect_features(
            threshold=threshold,
            margin=margin,
            min_distance=distance,
            placement='FRAME',
        )

        tracks_after = len(clip.tracking.tracks)
        features_created = tracks_after - base_count
        context.scene.new_marker_count = features_created
        logger.info(
            f"Detect Features erzeugte {features_created} Marker, "
            f"gespeichert: {context.scene.new_marker_count}"
        )
        if tracks_after == base_count:
            settings.default_pattern_size = max(
                1,
                int(settings.default_pattern_size / 1.1),
            )
            settings.default_search_size = settings.default_pattern_size * 2

        new_marker = tracks_after - base_count

        while context.scene.new_marker_count < min_new and threshold > 0.0001:
            if tracks_after == base_count:
                settings.default_pattern_size = max(
                    1,
                    int(settings.default_pattern_size / 1.1),
                )
                settings.default_search_size = settings.default_pattern_size * 2

            adjust_marker_count_plus(context.scene, context.scene.new_marker_count)
            min_plus = context.scene.min_marker_count_plus
            threshold = max(
                threshold * ((context.scene.new_marker_count + 0.1) / min_plus),
                0.0001,
            )

            margin, distance, _ = ensure_margin_distance(clip, threshold)

            # zuvor erstellte Marker entfernen
            for track in list(clip.tracking.tracks)[base_count:]:
                track.select = True
            bpy.ops.clip.delete_track()

            msg = (
                f"Nur {new_marker} Features, "
                f"senke Threshold auf {threshold:.4f}"
            )
            self.report({'INFO'}, msg)
            prev_count = tracks_after
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
                placement='FRAME',
            )
            tracks_after = len(clip.tracking.tracks)
            features_created = tracks_after - prev_count
            context.scene.new_marker_count = features_created
            new_marker = tracks_after - base_count
            logger.info(
                f"Detect Features erzeugte {features_created} Marker, "
                f"gespeichert: {context.scene.new_marker_count}"
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

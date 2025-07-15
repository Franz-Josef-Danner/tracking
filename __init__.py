bl_info = {
    "name": "Kaiserlich Tracksycle",
    "description": "Automated tracking cycle for Blender with proxy handling and dynamic feature detection.",
    "author": "Kaiserlich",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Clip Editor > Sidebar > Kaiserlich",
    "category": "Tracking",
}

try:
    import bpy
    from bpy.props import IntProperty, FloatProperty, BoolProperty, EnumProperty
except ModuleNotFoundError:  # pragma: no cover - allows running tests without Blender
    bpy = None
    IntProperty = FloatProperty = BoolProperty = EnumProperty = lambda *a, **k: None

from .modules.util.tracker_logger import configure_logger

from .modules.operators.tracksycle_operator import KAISERLICH_OT_auto_track_cycle
from .modules.operators.rename_tracks_modal import KAISERLICH_OT_rename_tracks_modal
from .modules.operators.detect_features_operator import KAISERLICH_OT_detect_features
from .modules.ui.kaiserlich_panel import KAISERLICH_PT_tracking_tools

classes = [
    KAISERLICH_OT_auto_track_cycle,
    KAISERLICH_OT_rename_tracks_modal,
    KAISERLICH_OT_detect_features,
    KAISERLICH_PT_tracking_tools,
]


def register():
    if bpy is None:
        raise RuntimeError("bpy module is required to register the add-on")

    configure_logger()

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.min_marker_count = IntProperty(
        name="Minimale Markeranzahl",
        description="Anzahl an erkannten Features, die mindestens erreicht werden soll",
        default=10,
        min=1,
    )

    bpy.types.Scene.min_track_length = IntProperty(
        name="Tracking-L\u00e4nge (min)",
        description="Minimale Anzahl Frames pro Marker",
        default=10,
        min=1,
    )

    bpy.types.Scene.error_threshold = FloatProperty(
        name="Fehler-Schwelle",
        description="Maximal tolerierter Reprojektionfehler",
        default=5.0,
        min=0.0,
    )

    bpy.types.Scene.debug_output = BoolProperty(
        name="\U0001F527 Debug Output aktivieren",
        description="Aktiviert ausführliches Logging zur Fehleranalyse",
        default=False,
    )

    bpy.types.Scene.proxy_built = BoolProperty(
        name="Proxy Built",
        description="Internal flag used by the modal proxy builder",
        default=False,
    )

    bpy.types.Scene.kaiserlich_feature_detection_done = BoolProperty(
        name="Feature Detection Done",
        description="Internal flag for async feature detection",
        default=False,
    )


    bpy.types.Scene.kaiserlich_tracking_state = EnumProperty(
        name="Tracking State",
        description="Internal state for the Kaiserlich Tracksycle operator",
        items=[
            ('WAIT_FOR_PROXY', 'Wait for Proxy', ''),
            ('DETECTING', 'Detecting', ''),
            ('TRACKING', 'Tracking', ''),
            ('CLEANUP', 'Cleanup', ''),
            ('REVIEW', 'Review', ''),
        ],
        default='WAIT_FOR_PROXY',
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.min_marker_count
    del bpy.types.Scene.min_track_length
    del bpy.types.Scene.error_threshold
    del bpy.types.Scene.debug_output
    del bpy.types.Scene.proxy_built
    del bpy.types.Scene.kaiserlich_feature_detection_done
    del bpy.types.Scene.kaiserlich_tracking_state


if __name__ == "__main__":
    register()


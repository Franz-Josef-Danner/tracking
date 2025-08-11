import bpy

from .tracker_settings import CLIP_OT_tracker_settings
from .detect import CLIP_OT_detect
from .bidirectional_track import CLIP_OT_bidirectional_track
from .clean_short_tracks import CLIP_OT_clean_short_tracks
from .tracking_pipeline import CLIP_OT_tracking_pipeline

# WICHTIG: beide Operatoren importieren
from .clean_error_tracks import (
    CLIP_OT_clean_error_tracks_modal,
    CLIP_OT_clean_error_tracks,
)

from .optimize_tracking_modal import CLIP_OT_optimize_tracking_modal
from .main import CLIP_OT_main

classes = (
    CLIP_OT_tracker_settings,
    CLIP_OT_detect,
    CLIP_OT_bidirectional_track,
    CLIP_OT_clean_short_tracks,
    CLIP_OT_tracking_pipeline,
    CLIP_OT_clean_error_tracks_modal,  # Modal zuerst ok
    CLIP_OT_clean_error_tracks,        # Starter ruft Modal
    CLIP_OT_optimize_tracking_modal,
    CLIP_OT_main,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()

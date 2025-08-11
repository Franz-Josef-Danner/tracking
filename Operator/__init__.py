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
        try:
            bpy.utils.register_class(cls)
            bn = getattr(cls, "bl_idname", cls.__name__)
            print(f"[tracking-final] Registered: {bn}")
        except Exception as e:
            print(f"[tracking-final] FAILED to register {cls}: {e}")

    # Sichtprüfung NACH der Registrierung
    try:
        print("[tracking-final] exists_modal:", hasattr(bpy.ops.clip, "clean_error_tracks_modal"))
        print("[tracking-final] exists_starter:", hasattr(bpy.ops.clip, "clean_error_tracks"))
    except Exception as e:
        print("[tracking-final] post-register check failed:", e)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"[tracking-final] FAILED to unregister {cls}: {e}")

if __name__ == "__main__":
    register()

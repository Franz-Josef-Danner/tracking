import bpy

from .marker_helper_main import CLIP_OT_marker_helper_main
from .solve_camera import CLIP_OT_solve_watch_clean, run_solve_watch_clean  # ✅ KORREKT
from .main import CLIP_OT_main

try:
    from .clean_short_tracks import CLIP_OT_clean_short_tracks
    _HAS_CLEAN_SHORT = True
except Exception as e:
    print(f"[WARN] clean_short_tracks nicht geladen: {e}")
    _HAS_CLEAN_SHORT = False


classes = (
    CLIP_OT_clean_short_tracks,
    CLIP_OT_marker_helper_main,
    CLIP_OT_solve_watch_clean,          # ✅ genau einmal
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

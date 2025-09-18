import bpy

from .tracking_coordinator import CLIP_OT_tracking_coordinator
from .bootstrap_O import CLIP_OT_bootstrap_cycle
from .find_frame_O import CLIP_OT_find_low_and_jump
from .detect_O import CLIP_OT_detect_cycle
from .clean_O import CLIP_OT_clean_cycle
from .solve_O import CLIP_OT_solve_cycle

classes = (
    CLIP_OT_bootstrap_cycle,
    CLIP_OT_find_low_and_jump,
    CLIP_OT_detect_cycle,
    CLIP_OT_clean_cycle,
    CLIP_OT_solve_cycle,
    CLIP_OT_tracking_coordinator,
)

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

if __name__ == "__main__":
    register()

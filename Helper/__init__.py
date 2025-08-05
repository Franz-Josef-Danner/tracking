from .marker_helper_main import CLIP_OT_marker_helper_main
from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .error_value import CLIP_OT_error_value
from .set_test_value import CLIP_OT_set_test_value

operator_classes = (
    marker_helper_main,
    enable_proxy,
    disable_proxy,
    error_value,
    set_test_value;
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

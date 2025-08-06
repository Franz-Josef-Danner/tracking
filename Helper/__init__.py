from .marker_helper_main import CLIP_OT_marker_helper_main
from .disable_proxy import CLIP_OT_disable_proxy
from .enable_proxy import CLIP_OT_enable_proxy
from .error_value import error_value
from .set_test_value import set_test_value
from .find_low_marker_frame import find_low_marker_frame
from .jump_to_frame import jump_to_frame
from .properties import RepeatEntry

operator_classes = (
    marker_helper_main,
    enable_proxy,
    disable_proxy,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        bpy.types.Scene.repeat_frame = bpy.props.CollectionProperty(type=RepeatEntry)
        bpy.utils.register_class(CLIP_OT_main)  # oder dein gesamter Operator-Block


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        bpy.utils.unregister_class(RepeatEntry)
        bpy.utils.unregister_class(CLIP_OT_main)

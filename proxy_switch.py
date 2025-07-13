import bpy
import logging
from .utils import get_active_clip

logger = logging.getLogger(__name__)

class ToggleProxyOperator(bpy.types.Operator):
    """Proxy/Timecode Umschalten"""
    bl_idname = "clip.toggle_proxy"
    bl_label = "Toggle Proxy/Timecode"

    def execute(self, context):
        """Toggle proxy usage on the active clip.

        The operator may be executed from a timer or other context where
        ``context.space_data`` is unavailable. In that case fall back to the
        scene's active clip if possible.
        """

        clip = get_active_clip(context)

        if clip:
            before = clip.use_proxy
            clip.use_proxy = not before
            state = "aktiviert" if clip.use_proxy else "deaktiviert"
            logger.info("Proxy/Timecode umschalten: %s -> %s", before, clip.use_proxy)
            self.report({'INFO'}, f"Proxy/Timecode {state}")
        else:
            logger.warning("Proxy/Timecode kann nicht umgeschaltet werden: kein Clip")
            self.report({'WARNING'}, "Kein Clip geladen")
        return {'FINISHED'}

def draw_proxy_button(self, context):
    layout = self.layout
    layout.operator(ToggleProxyOperator.bl_idname, text="Proxy/Timecode umschalten")

def register():
    bpy.utils.register_class(ToggleProxyOperator)
    bpy.types.CLIP_HT_header.append(draw_proxy_button)

def unregister():
    bpy.types.CLIP_HT_header.remove(draw_proxy_button)
    bpy.utils.unregister_class(ToggleProxyOperator)

if __name__ == "__main__":
    register()

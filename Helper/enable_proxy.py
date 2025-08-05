import bpy

class CLIP_OT_proxy_disable(bpy.types.Operator):
    bl_idname = "clip.enable_proxy"
    bl_label = "Proxy Aktivieren"

def enable_proxy(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        print("Kein gültiger Movie Clip gefunden.")
        return

    clip.use_proxy = True
    print("Proxy aktivieren.")

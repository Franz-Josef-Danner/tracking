import bpy

class CLIP_OT_proxy_disable(bpy.types.Operator):
    bl_idname = "clip.proxy_disable"
    bl_label = "Proxy Deaktivieren"

def disable_proxy(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        print("Kein gültiger Movie Clip gefunden.")
        return

    clip.use_proxy = False
    print("Proxy deaktiviert.")

import bpy

class CLIP_OT_proxy_disable(bpy.types.Operator):
    bl_idname = "clip.proxy_disable"
    bl_label = "Proxy Deaktivieren"

def enable_proxy(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        print("Kein gültiger Movie Clip gefunden.")
        return

    clip.use_proxy = True
    for proxy in clip.proxy.proxy_storage:
        proxy.build_25 = True
        proxy.build_50 = True
        proxy.build_75 = True
        proxy.build_100 = True
    print("Proxy aktiviert.")

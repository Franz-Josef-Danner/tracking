import bpy

def disable_proxy(context):
    clip = getattr(context.space_data, "clip", None)
    if not clip:
        print("Kein gültiger Movie Clip gefunden.")
        return

    clip.use_proxy = False
    print("Proxy deaktiviert.")

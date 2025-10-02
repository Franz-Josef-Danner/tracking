import bpy

def bootstrap(context):
    clip = context.edit_movieclip
    scene = context.scene

    if clip is None:
        raise RuntimeError("Kein Movie Clip aktiv im Clip Editor.")

    hz, vc = clip.size  # width, height
    ma = hz * 0.025
    md = hz * 0.025
    pz = hz * 0.01
    sz = pz * 2
    tr = 1.0

    ef = getattr(scene, 'kaiserlich_marker_per_frame', 25)
    za = (ef * 4) / 14
    og = za * 1.1
    ug = za * 0.9

    return {
        "hz": hz, "vc": vc, "ma": ma, "md": md,
        "pz": pz, "sz": sz, "tr": tr,
        "za": za, "og": og, "ug": ug
    }

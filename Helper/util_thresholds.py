import bpy

def set_all_thresholds_to_one(context: bpy.types.Context) -> None:
    scene = context.scene
    props = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    for p in props:
        if hasattr(scene, p):
            try:
                setattr(scene, p, 1.0)
            except Exception:
                pass

def snapshot_thresholds(scene: bpy.types.Scene):
    keys = (
        "kaiserlich_rot_thresh_x",
        "kaiserlich_rot_thresh_y",
        "kaiserlich_scale_thresh_min",
        "kaiserlich_scale_thresh_max",
        "kaiserlich_rot_scale_thresh_rot",
        "kaiserlich_rot_scale_thresh_scale",
        "kaiserlich_perspective_thresh",
    )
    snap = {}
    for k in keys:
        try:
            snap[k] = float(getattr(scene, k))
        except Exception:
            pass
    return snap

def restore_thresholds(scene: bpy.types.Scene, snap: dict):
    for k, v in snap.items():
        try:
            if hasattr(scene, k):
                setattr(scene, k, float(v))
        except Exception:
            pass
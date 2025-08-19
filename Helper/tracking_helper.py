# In Helper/tracking_helper.py
def track_to_scene_end_fn(context, *, coord_token: str = "") -> dict:
    handles = _clip_editor_handles(context)
    if not handles:
        raise RuntimeError("Kein CLIP_EDITOR im aktuellen Window gefunden")

    scene = context.scene
    wm = context.window_manager
    start_frame = int(scene.frame_current)
    end_frame = int(scene.frame_end)

    with context.temp_override(**handles):
        bpy.ops.clip.track_markers(
            'INVOKE_DEFAULT',
            backwards=False,
            sequence=True,
        )

    tracked_until = int(context.scene.frame_current)
    scene.frame_set(start_frame)

    if coord_token:
        wm["bw_tracking_done_token"] = coord_token
    info = {
        "start_frame": start_frame,
        "tracked_until": tracked_until,
        "scene_end": end_frame,
        "backwards": False,
        "sequence": True,
    }
    wm["bw_tracking_last_info"] = info
    return info

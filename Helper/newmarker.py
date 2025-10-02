def newmarker(context):
    clip = context.edit_movieclip
    if clip is None:
        return []
    current_frame = context.scene.frame_current
    return [marker for track in clip.tracking.tracks
                   for marker in track.markers
                   if marker.frame == current_frame]

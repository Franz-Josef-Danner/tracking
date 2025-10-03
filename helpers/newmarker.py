def newmarker(context):
    # identisch zu snapshot; getrennt belassen für semantische Klarheit
    clip = context.edit_movieclip
    current_frame = context.scene.frame_current
    return [marker for track in clip.tracking.tracks
                   for marker in track.markers
                   if marker.frame == current_frame]

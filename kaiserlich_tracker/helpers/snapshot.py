def snapshot(context):
    space = context.space_data
    clip = space.clip
    current_frame = context.scene.frame_current
    lm = [marker
          for track in clip.tracking.tracks
          for marker in track.markers
          if marker.frame == current_frame]
    print(f'[Kaiserlich][snapshot] {len(lm)} markers altes Set')
    return lm

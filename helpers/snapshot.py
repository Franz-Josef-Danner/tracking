def snapshot(context):
    space = context.space_data
    clip = space.clip
    current_frame = context.scene.frame_current
    # Nur aktive (nicht gemutete) Marker
    lm = [marker
          for track in clip.tracking.tracks
          for marker in track.markers
          if marker.frame == current_frame and not getattr(marker, 'mute', False)]
    print(f'[Kaiserlich][snapshot] {len(lm)} aktive Marker altes Set')
    return lm

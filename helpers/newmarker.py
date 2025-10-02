def newmarker(context):
    space = context.space_data
    clip = space.clip
    current_frame = context.scene.frame_current
    nm = [marker
          for track in clip.tracking.tracks
          for marker in track.markers
          if marker.frame == current_frame]
    print(f'[Kaiserlich][newmarker] {len(nm)} neue Marker gefunden')
    return nm

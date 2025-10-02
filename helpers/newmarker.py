def newmarker(context, previous):
    """Liefert wirklich neue, aktive Marker (nicht in previous, nicht gemutet)."""
    prev_ids = {id(m) for m in previous}
    space = context.space_data
    clip = space.clip
    current_frame = context.scene.frame_current
    nm = [marker
          for track in clip.tracking.tracks
          for marker in track.markers
          if marker.frame == current_frame and id(marker) not in prev_ids and not getattr(marker, 'mute', False)]
    print(f'[Kaiserlich][newmarker] {len(nm)} neue Marker gefunden')
    return nm

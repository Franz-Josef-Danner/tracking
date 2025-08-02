import bpy


def apply_pattern_plus():
    """
    Erhöht das Pattern-Size von Tracks mit Pattern Match == 'SADDLE'.
    Diese Funktion ersetzt den früheren Direktcode beim Import.
    """
    if bpy.context.area is None or bpy.context.area.type != 'CLIP_EDITOR':
        print("Bitte Clip Editor aktivieren.")
        return

    clip = bpy.context.space_data.clip
    if clip is None:
        print("Kein Movie Clip aktiv.")
        return

    for tracking_object in clip.tracking.objects:
        for track in tracking_object.tracks:
            if track.pattern_match == 'SADDLE':
                track.pattern_size *= 1.1
                print(f"Track {track.name}: Neue Pattern Size = {track.pattern_size}")

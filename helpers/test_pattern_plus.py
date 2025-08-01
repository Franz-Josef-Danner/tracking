import bpy

# Sicherstellen, dass wir uns im Clip Editor befinden
if bpy.context.area.type != 'CLIP_EDITOR':
    print("Bitte Clip Editor aktivieren.")
else:
    clip = bpy.context.space_data.clip
    if clip is None:
        print("Kein Movie Clip aktiv.")
    else:
        for tracking_object in clip.tracking.objects:
            for track in tracking_object.tracks:
                if track.is_enabled and track.pattern_match == 'SADDLE':
                    old_size = track.pattern_size
                    track.pattern_size *= 1.1
                    print(f"Track '{track.name}': Pattern Size {old_size} → {track.pattern_size}")
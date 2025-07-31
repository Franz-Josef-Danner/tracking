import bpy

def delete_selected_tracks():
    clip = bpy.context.space_data.clip
    tracks = clip.tracking.tracks
    to_delete = [t for t in tracks if t.select]
    for t in to_delete:
        tracks.remove(t)

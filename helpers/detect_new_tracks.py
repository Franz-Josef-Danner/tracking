import bpy
from .delete_tracks import delete_selected_tracks


def detect_new_tracks(clip, detection_threshold, min_distance, margin):
    """Detect features and return new tracks and the state before detection."""
    names_before = {t.name for t in clip.tracking.tracks}
    if bpy.ops.clip.proxy_off.poll():
        bpy.ops.clip.proxy_off()
    print(
        f"[Detect Features] threshold {detection_threshold:.8f}, margin {margin}, min_distance {min_distance}"
    )
    bpy.ops.clip.detect_features(
        threshold=detection_threshold,
        min_distance=min_distance,
        margin=margin,
    )
    print(
        f"[Detect Features] finished threshold {detection_threshold:.8f}, margin {margin}, min_distance {min_distance}"
    )
    names_after = {t.name for t in clip.tracking.tracks}
    new_tracks = [t for t in clip.tracking.tracks if t.name in names_after - names_before]
    return new_tracks, names_before

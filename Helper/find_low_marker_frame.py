# Helper/find_low_marker_frame.py
import bpy
from .jump_to_frame import jump_to_frame_helper

__all__ = ("find_low_marker_frame_core", "run_find_low_marker_frame")

def find_low_marker_frame_core(clip, *, marker_basis=20, frame_start=None, frame_end=None):
    """Gibt den ersten Frame < marker_basis zurück oder None."""
    tracking = clip.tracking
    tracks = tracking.tracks

    if frame_start is None:
        frame_start = clip.frame_start
    if frame_end is None:
        frame_end = bpy.context.scene.frame_end

    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {marker_basis}")
    for frame in range(frame_start, frame_end + 1):
        count = 0
        for track in tracks:
            if track.markers.find_frame(frame):
                count += 1
        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < marker_basis:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame
    return None

def _get_clip(context):
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None

def run_find_low_marker_frame(
    context,
    *,
    use_scene_basis: bool = True,
    marker_basis: int = 20,
    frame_start: int = -1,
    frame_end: int = -1,
):
    """
    Sucht ersten Frame mit weniger als 'marker_basis' Markern (ggf. aus Scene['marker_basis']).
    Bei Treffer: setzt scene['goto_frame'] und ruft jump_to_frame.
    Bei keinem Treffer: startet solve_watch_clean.
    """
    clip = _get_clip(context)
    if clip is None:
        print("Error: Kein aktiver MovieClip gefunden.")
        return None

    scene = context.scene
    basis = int(scene.get("marker_basis", marker_basis)) if use_scene_basis else int(marker_basis)
    fs = None if frame_start < 0 else frame_start
    fe = None if frame_end < 0 else frame_end

    low_frame = find_low_marker_frame_core(clip, marker_basis=basis, frame_start=fs, frame_end=fe)

    if low_frame is not None:
        scene["goto_frame"] = int(low_frame)
        print(f"[MarkerCheck] Treffer: Low-Marker-Frame {low_frame}. Übergabe an jump_to_frame …")
        try:
            bpy.ops.clip.jump_to_frame('EXEC_DEFAULT', target_frame=int(low_frame))
        except Exception as ex:
            print(f"Error: jump_to_frame fehlgeschlagen: {ex}")
            return None
        return low_frame

    print("[MarkerCheck] Keine Low-Marker-Frames gefunden. Starte Kamera-Solve.")
    try:
        bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')
    except Exception as ex:
        print(f"Error: Solve-Start fehlgeschlagen: {ex}")
        return None
    return None

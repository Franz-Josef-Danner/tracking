# Helper/find_low_marker_frame.py
import bpy
from .jump_to_frame import jump_to_frame_helper           # bereits zu Helper migriert
from .solve_camera import run_solve_watch_clean  # am Dateianfang


__all__ = ("run_find_low_marker_frame", "find_low_marker_frame_core")

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
    Bei Treffer: setzt scene['goto_frame'] und ruft jump_to_frame_helper.
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
        print(f"[MarkerCheck] Treffer: Low-Marker-Frame {low_frame}. Übergabe an jump_to_frame (Helper) …")
        try:
            res = run_jump_to_frame(context, frame=int(low_frame))
            return low_frame
        except Exception as ex:
            print(f"Error: jump_to_frame (Helper) Exception: {ex}")
            return None
    else:
        print("[MarkerCheck] Keine Low-Marker-Frames gefunden. Starte Kamera-Solve (Helper).")
        try:
            # Einheitliche Benennung: nutze die Variante, die es bei dir gibt
            ok = run_solve_watch_clean(context)   # oder: solve_watch_clean(context)
        except Exception as ex:
            print(f"Error: Solve-Start (Helper) Exception: {ex}")
            return None
        if not ok:
            print("Error: Solve-Start (Helper) meldete False")
        return None



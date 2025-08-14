# Helper/find_low_marker_frame.py
import bpy
from .jump_to_frame import run_jump_to_frame           # bereits zu Helper migriert
from .solve_camera import run_solve_watch_clean        # Helper-Variante

__all__ = ("run_find_low_marker_frame", "find_low_marker_frame_core")

def find_low_marker_frame_core(clip, *, marker_basis=20, frame_start=None, frame_end=None):
    """
    Gibt den ersten Frame < marker_basis zurück oder None.
    Implementierung entspricht der bewährten Zähllogik der alten Version.
    """
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
            # identisch zur alten, stabilen Routine: Markerexistenz via find_frame
            if track.markers.find_frame(frame):
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < marker_basis:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Kein Frame mit zu wenigen Markern gefunden.")
    return None


def _get_clip(context):
    """
    Robust: zuerst aktiven Clip aus dem CLIP_EDITOR nehmen, sonst erstes MovieClip-Datablock.
    """
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
    Bei Treffer:
      - setzt scene['goto_frame']
      - ruft run_jump_to_frame(context, frame=…)
    Bei keinem Treffer:
      - ruft run_solve_watch_clean(context)
    Rückgabe:
      - int (Frame) bei Treffer
      - None, wenn kein Low-Marker-Frame gefunden wurde oder bei Fehler
    """
    clip = _get_clip(context)
    if clip is None:
        print("Error: Kein aktiver MovieClip gefunden.")
        return None

    scene = context.scene
    basis = int(scene.get("marker_basis", marker_basis)) if use_scene_basis else int(marker_basis)
    fs = None if frame_start < 0 else int(frame_start)
    fe = None if frame_end < 0 else int(frame_end)

    low_frame = find_low_marker_frame_core(clip, marker_basis=basis, frame_start=fs, frame_end=fe)

    # Kein Treffer → Solve starten (Helper)
    print("[MarkerCheck] Keine Low-Marker-Frames gefunden. Starte Kamera-Solve (Helper).")
    try:
        ok = run_solve_watch_clean(context)  # Helper-API
        if not ok:
            print("Error: Solve-Start (Helper) meldete False")
    except Exception as ex:
        print(f"Error: Solve-Start (Helper) Exception: {ex}")
    return None

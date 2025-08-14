# Helper/find_low_marker_frame.py
import bpy

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
        # defensive: nutze Scene.frame_end
        scn = bpy.context.scene if hasattr(bpy.context, "scene") else None
        frame_end = getattr(scn, "frame_end", clip.frame_start)

    print(f"[MarkerCheck] Erwartete Mindestmarker pro Frame: {int(marker_basis)}")
    for frame in range(int(frame_start), int(frame_end) + 1):
        count = 0
        for track in tracks:
            # identisch zur alten, stabilen Routine: Markerexistenz via find_frame
            if track.markers.find_frame(frame):
                count += 1

        print(f"[MarkerCheck] Frame {frame}: {count} aktive Marker")
        if count < marker_basis:
            print(f"[MarkerCheck] → Zu wenige Marker in Frame {frame}")
            return frame

    print("[MarkerCheck] Keine Low-Marker-Frames gefunden.")
    return None


def _get_clip(context):
    """
    Robust: zuerst aktiven Clip aus dem CLIP_EDITOR nehmen, sonst erstes MovieClip-Datablock.
    """
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _effective_threshold(scene, marker_basis: int) -> int:
    """
    EIN wirksamer Grenzwert:
    - bevorzugt scene['marker_adapt'] (falls numerisch),
    - sonst marker_basis.
    """
    val = scene.get("marker_adapt", None)
    if isinstance(val, (int, float)):
        return max(1, int(val))
    return max(1, int(marker_basis))


def run_find_low_marker_frame(
    context,
    *,
    use_scene_basis: bool = True,
    marker_basis: int = 20,
    frame_start: int = -1,
    frame_end: int = -1,
):
    """
    Sucht den ERSTEN Frame unterhalb der wirksamen Schwelle und liefert
    ein Status-Dict für den Coordinator:

      {"status": "FOUND", "frame": <int>}
      {"status": "NONE"}                 – kein Low-Marker-Frame im Bereich
      {"status": "FAILED", "reason": "..."} – Fehlerfall

    WICHTIG:
    - Kein jump_to_frame() und kein Solve hier; das macht der Coordinator.
    - Speichern/Verwalten von Frames findet NUR nach bestätigtem Jump statt.
    """
    try:
        clip = _get_clip(context)
        if clip is None:
            return {"status": "FAILED", "reason": "Kein aktiver MovieClip gefunden."}

        scene = context.scene
        basis = int(scene.get("marker_basis", marker_basis)) if use_scene_basis else int(marker_basis)
        fs = None if frame_start < 0 else int(frame_start)
        fe = None if frame_end < 0 else int(frame_end)

        # EINDEUTIGE Schwelle mit Priorität marker_adapt
        threshold = _effective_threshold(scene, basis)

        low_frame = find_low_marker_frame_core(
            clip,
            marker_basis=threshold,
            frame_start=fs,
            frame_end=fe,
        )

        if low_frame is None:
            # Log bleibt wie in deinem bisherigen Output
            print("[MarkerCheck] Keine Low-Marker-Frames gefunden. Starte Kamera-Solve (Helper).")
            return {"status": "NONE"}

        # Coordinator setzt goto_frame und springt danach
        return {"status": "FOUND", "frame": int(low_frame)}

    except Exception as ex:
        return {"status": "FAILED", "reason": str(ex)}

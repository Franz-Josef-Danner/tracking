import bpy
from mathutils import Vector

def cleanup_new_markers_at_frame(context, *, pre_ptrs, frame, min_distance=0.01, distance_unit='normalized'):
    """
    Löscht neue Marker, die innerhalb des angegebenen Mindestabstands zu alten (nicht gemuteten) Markern liegen.
    Selektiert alle verbliebenen neuen Marker.
    - pre_ptrs: Set der Track-Pointer vor der Marker-Erzeugung.
    - frame: Frame, an dem verglichen wird.
    - min_distance: Mindestabstand (je nach Einheit "normalized" oder "pixel").
    """
    scn = context.scene
    clip = context.edit_movieclip or getattr(context.space_data, 'clip', None) or getattr(scn, 'clip', None)
    if not clip:
        return {"status": "FAILED", "reason": "no_clip"}

    def dist2(a: Vector, b: Vector, clip_size):
        if distance_unit == "pixel" and clip_size:
            width, height = clip_size
            dx = (a.x - b.x) * width
            dy = (a.y - b.y) * height
            return dx*dx + dy*dy
        # normalized
        return (a.x - b.x)**2 + (a.y - b.y)**2

    # alte Marker-Koordinaten sammeln
    old_positions = []
    for tr in clip.tracking.tracks:
        if tr.as_pointer() in pre_ptrs:
            m = tr.markers.find_frame(frame, exact=True)
            if m and not m.mute:  # nicht gemutet
                old_positions.append(m.co.copy())

    # neue Tracks ermitteln (nicht im Snapshot)
    new_tracks = [tr for tr in clip.tracking.tracks if tr.as_pointer() not in pre_ptrs]

    min_d2 = min_distance * min_distance
    clip_size = (float(clip.size[0]), float(clip.size[1])) if distance_unit == "pixel" else None

    removed = 0
    kept = 0

    for tr in new_tracks:
        m = tr.markers.find_frame(frame, exact=True)
        if not m:
            continue  # kein Marker im aktuellen Frame

        pos = m.co.copy()
        # Distanz zum nächsten alten Marker bestimmen
        too_close = False
        for old_pos in old_positions:
            if dist2(pos, old_pos, clip_size) < min_d2:
                too_close = True
                break

        if too_close:
            # Marker löschen
            tr.markers.delete_frame(frame)
            removed += 1
        else:
            # Marker selektieren
            try:
                m.select = True
                tr.select = True
            except Exception:
                pass
            kept += 1

    return {
        "status": "OK",
        "removed": removed,
        "kept": kept,
        "old_count": len(old_positions),
        "new_total": len(new_tracks),
    }

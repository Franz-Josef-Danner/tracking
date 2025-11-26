# Helper/correct_selected_by_ref_dynamic.py
# ------------------------------------------------------------
import bpy
import math
from typing import List, Tuple, Optional


# ------------------------------------------------------------
# INTERNAL: get active valid marker location for a track at frame
# ------------------------------------------------------------
def _get_marker(track: bpy.types.MovieTrackingTrack, frame: int) -> Optional[Tuple[float, float]]:
    try:
        m = track.markers.find_frame(frame)
        if m is None or m.mute or not m.enabled:
            return None
        return (m.co[0], m.co[1])
    except Exception:
        return None


# ------------------------------------------------------------
# INTERNAL: distance
# ------------------------------------------------------------
def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ------------------------------------------------------------
# MAIN HELPER (dynamischer Korrekturalgorithmus)
# ------------------------------------------------------------
def correct_motion_by_dynamic_reference(context: bpy.types.Context,
                                        max_near_dist: float = 0.25):
    """
    Dynamische Korrektur selektierter Marker auf Basis relativer Positionen zu 3 Ref-Tracks.

    Logik:
    - Es werden Ref-Tracks gesucht, die bei f, f-1, f-2 aktive Marker haben.
    - Für jeden selektierten Track wird die Abweichung am aktuellen Frame f
      zu den 3 nächsten Referenzen berechnet (x und y separat).
    - Retush pro Achse: ret = 1 - Differenz
      => niemals 0, kein Clamp nötig.
    - new = sel / ret
    - Dadurch wird der Marker bei starken Abweichungen adaptiert,
      bleibt aber stabil, wenn die Differenz gering ist.
    """

    scene = context.scene
    clip = context.space_data.clip
    if clip is None:
        return {"CANCELLED"}

    tracking = clip.tracking
    tracks = tracking.tracks

    f = scene.frame_current
    f1 = f - 1
    f2 = f - 2

    # 1) Selektiert
    selected_tracks = [t for t in tracks if t.select and not t.lock and not t.mute]

    if not selected_tracks:
        return {"CANCELLED"}

    # 2) Referenzen sammeln
    ref_tracks = []
    for t in tracks:
        if t.lock or t.mute or t.select:
            continue
        p0 = _get_marker(t, f)
        p1 = _get_marker(t, f1)
        p2 = _get_marker(t, f2)
        if p0 and p1 and p2:
            ref_tracks.append((t, (p0, p1, p2)))

    if not ref_tracks:
        return {"CANCELLED"}

    # 3) Prozess pro selektierten Track
    for st in selected_tracks:
        p0s = _get_marker(st, f)
        if not p0s:
            continue

        # 3.1) Nahe Ref-Tracks finden
        nearest = []
        for t, (p0, p1, p2) in ref_tracks:
            d = _dist(p0s, p0)
            if d <= max_near_dist:
                nearest.append((d, p0))

        if len(nearest) < 3:
            continue

        nearest.sort(key=lambda x: x[0])
        nearest = nearest[:3]

        # 3.2) Durchschnittsposition der Ref-Marker bei f
        avg_ref_x = sum(p[0] for (_, p) in nearest) / 3.0
        avg_ref_y = sum(p[1] for (_, p) in nearest) / 3.0

        # 3.3) Differenzen
        dx = abs(avg_ref_x - p0s[0])
        dy = abs(avg_ref_y - p0s[1])

        # 3.4) Retush (niemals 0 → mathematisch sicher)
        ret_x = 1.0 - dx
        ret_y = 1.0 - dy

        # 3.5) Neue Position
        new_x = p0s[0] / ret_x
        new_y = p0s[1] / ret_y

        # 3.6) Update
        mk = st.markers.find_frame(f)
        if mk:
            mk.co[0] = new_x
            mk.co[1] = new_y

    return {"FINISHED"}

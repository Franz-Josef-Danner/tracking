# Helper/correct_selected_by_ref_motion_backward.py
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
# INTERNAL: distance + vector operations
# ------------------------------------------------------------
def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _vec(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (b[0] - a[0], b[1] - a[1])


def _avg_vec(vecs: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not vecs:
        return (0.0, 0.0)
    return (sum(v[0] for v in vecs) / len(vecs),
            sum(v[1] for v in vecs) / len(vecs))


def _avg_pos(pos: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not pos:
        return (0.0, 0.0)
    return (sum(p[0] for p in pos) / len(pos),
            sum(p[1] for p in pos) / len(pos))


# ------------------------------------------------------------
# MAIN HELPER FUNCTION (BACKWARD)
# ------------------------------------------------------------
def correct_motion_by_reference_backward(context: bpy.types.Context,
                                         max_near_dist: float = 0.25,
                                         min_vec_diff: float = 0.05):
    """
    Korrigiert Positionen selektierter Marker beim Rückwärts-Tracking
    anhand der Bewegungsvektoren der 3 nächstliegenden Referenz-Tracks.

    Bedingungen:
    - Ref-Tracks benötigen aktive Marker bei f, f+1, f+2
    - Selektierte Marker brauchen aktive Marker bei f, f+1 (für Rückwärtsrichtung)
    - Nur Ref unter max_near_dist berücksichtigen
    - Korrektur nur wenn Vektorabweichung > min_vec_diff
    - Projektion nutzt Durchschnitt ref-Bewegung f+2 → f+1 auf Position bei f
    """

    scene = context.scene
    clip = context.space_data.clip
    if clip is None:
        return {"CANCELLED"}

    tracking = clip.tracking
    tracks = tracking.tracks

    f = scene.frame_current
    f1 = f + 1
    f2 = f + 2

    # ------------------------------------------------------------
    # 1) Selektierte Tracks
    # ------------------------------------------------------------
    selected_tracks = [t for t in tracks if t.select and not t.mute and not t.lock]

    # ------------------------------------------------------------
    # 2) Ref-Tracks sammeln
    # ------------------------------------------------------------
    ref_tracks = []
    for t in tracks:
        if t.mute or t.lock or t.select:
            continue  # Niemals selektierte als Ref nehmen
        p0 = _get_marker(t, f)   # current
        p1 = _get_marker(t, f1)  # next
        p2 = _get_marker(t, f2)  # next+1
        if p0 and p1 and p2:
            ref_tracks.append((t, (p0, p1, p2)))

    if not ref_tracks:
        return {"CANCELLED"}

    # ------------------------------------------------------------
    # Verarbeitung selektierter Marker
    # ------------------------------------------------------------
    for st in selected_tracks:
        p0s = _get_marker(st, f)   # current
        p1s = _get_marker(st, f1)  # next (für Rückwärts-Vektor)

        if not (p0s and p1s):
            continue

        # Bewegungsvektor rückwärts: (f → f-1) = f → next in NEGATIV Richtung
        # üblich: backward = (p0s - p1s)
        vec_sel = _vec(p1s, p0s)  # p1 → p0

        # ------------------------------------------------------------
        # 3) Nächste Ref-Tracks aus Distanz bei f
        # ------------------------------------------------------------
        nearest = []
        for t, (p0, p1, p2) in ref_tracks:
            d = _dist(p0s, p0)
            if d <= max_near_dist:
                nearest.append((d, t, (p0, p1, p2)))

        if len(nearest) < 3:
            continue

        nearest.sort(key=lambda x: x[0])
        nearest = nearest[:3]

        # ------------------------------------------------------------
        # 4) Durchschnittlicher Bewegungsvektor (rückwärts)
        # Ref rückwärts: Bewegung von f1 → f0 = vec(p1 → p0)
        ref_vecs = [_vec(pos[1], pos[0]) for (_, _, pos) in nearest]
        avg_ref_vec = _avg_vec(ref_vecs)

        # Abweichung zwischen Selektiert und Ref
        diff_mag = math.hypot(vec_sel[0] - avg_ref_vec[0],
                              vec_sel[1] - avg_ref_vec[1])

        if diff_mag < min_vec_diff:
            continue  # keine Korrektur notwendig

        # ------------------------------------------------------------
        # 5) Projektion auf f aus Ref-Bewegung f2 → f1
        # ------------------------------------------------------------
        avg_f2 = _avg_pos([pos[2] for (_, _, pos) in nearest])  # f+2
        avg_f1 = _avg_pos([pos[1] for (_, _, pos) in nearest])  # f+1

        proj_vec = _vec(avg_f2, avg_f1)  # Bewegung zurück projizieren
        new_pos = (p0s[0] + proj_vec[0], p0s[1] + proj_vec[1])

        # ------------------------------------------------------------
        # ∎ ACTUAL UPDATE
        # ------------------------------------------------------------
        mk = st.markers.find_frame(f)
        if mk:
            mk.co[0] = new_pos[0]
            mk.co[1] = new_pos[1]

    return {"FINISHED"}
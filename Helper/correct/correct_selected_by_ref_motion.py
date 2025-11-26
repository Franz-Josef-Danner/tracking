# Helper/correct_selected_by_ref_motion.py
# ------------------------------------------------------------
import bpy
import math
from typing import List, Tuple, Optional


# ------------------------------------------------------------
# INTERNAL: get active valid marker location for a track at frame
# ------------------------------------------------------------
def _get_marker(track: bpy.types.MovieTrackingTrack, frame: int) -> Optional[Tuple[float, float]]:
    # ⚠ track.mute existiert nicht, nur Marker haben mute/disable
    # selecting disqualifies nicht – nur Marker selbst
    # retrieve marker at exact frame index
    try:
        m = track.markers.find_frame(frame)
        if m is None or m.mute or not m.enabled:
            return None
        return (m.co[0], m.co[1])
    except Exception:
        return None
#
# NEW: check if track is valid at a given frame
#
def _is_active_track(track: bpy.types.MovieTrackingTrack, frame: int) -> bool:
    if not track.select or track.lock:
        return False
    try:
        mk = track.markers.find_frame(frame)
        if not mk:
            return False
        if getattr(mk, "mute", False) or not getattr(mk, "enabled", True):
            return False
        return True
    except Exception:
        return False

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
            sum(p[1] for p in pos) / len(p))


# ------------------------------------------------------------
# MAIN HELPER FUNCTION
# ------------------------------------------------------------
def correct_motion_by_reference(context: bpy.types.Context,
                                max_near_dist: float = 0.25,
                                min_vec_diff: float = 0.05):
    """
    Korrigiert die Position selektierter Marker anhand der Bewegungsvektoren
    der 3 nächstliegenden Referenz-Tracks (current + 1 frame davor + 2 davor).

    Anforderungen exakt nach User-Spezifikation:
    - Nur Tracks als "ref" nutzbar, die bei f, f-1, f-2 aktive, ungemutete Marker besitzen
    - Nur selektierte Tracks bearbeiten
    - 3 nächstliegende ref suchen unter max_near_dist
    - Vergleich der Bewegungsvektoren
    - Wenn Abweichung > min_vec_diff → Korrektur
    - Korrektur erfolgt durch Projektion aus durchschnittlicher ref-Bewegung
      zwischen f-2, f-1 und f
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

    # --------------------------
    # 1) Selektierte Tracks erfassen
    # --------------------------
    # FIX: kein t.mute, sondern Marker prüfen → _is_active_track()
    selected_tracks = [t for t in tracks if _is_active_track(t, f)]

    # --------------------------
    # 2) Referenz-Tracks ermitteln
    # --------------------------
    ref_tracks = []
    for t in tracks:
        # FIX: t.mute existiert nicht → skip nur anhand Lock & Auswahl
        if t.lock or t.select:
            continue  # ref dürfen NICHT selektiert sein
        p0 = _get_marker(t, f)
        p1 = _get_marker(t, f1)
        p2 = _get_marker(t, f2)
        if p0 and p1 and p2:
            ref_tracks.append((t, (p0, p1, p2)))

    if not ref_tracks:
        return {"CANCELLED"}

    # --------------------------
    # Verarbeitung pro selektierten Track
    # --------------------------
    for st in selected_tracks:
        p0s = _get_marker(st, f)   # current
        p1s = _get_marker(st, f1)  # prev
        p2s = _get_marker(st, f2)  # prev2

        if not (p0s and p1s and p2s):
            continue

        # Bewegungsvektor des selektierten Tracks
        vec_sel = _vec(p1s, p0s)

        # --------------------------
        # 3) Distanz zu ref-Markern am aktuellen Frame
        # --------------------------
        nearest = []
        for t, (p0, p1, p2) in ref_tracks:
            d = _dist(p0s, p0)
            if d <= max_near_dist:
                nearest.append((d, t, (p0, p1, p2)))

        if len(nearest) < 3:
            continue  # nicht genügend Bezugspunkte

        nearest.sort(key=lambda x: x[0])
        nearest = nearest[:3]

        # --------------------------
        # 4) Durchschnitt der ref-Bewegungsvektoren vergleichen
        # --------------------------
        ref_vecs = [_vec(pos[1], pos[0]) for (_, _, pos) in nearest]
        avg_ref_vec = _avg_vec(ref_vecs)

        diff_mag = math.hypot(vec_sel[0] - avg_ref_vec[0],
                              vec_sel[1] - avg_ref_vec[1])

        if diff_mag < min_vec_diff:
            continue  # keine Korrektur nötig

        # --------------------------
        # 5) Korrekturprojektion aus ref-Positionen
        # --------------------------
        # Durchschnitt x,y auf f-2 und f-1 als Ursprung der Bewegung
        avg_f2 = _avg_pos([pos[2] for (_, _, pos) in nearest])
        avg_f1 = _avg_pos([pos[1] for (_, _, pos) in nearest])

        proj_vec = _vec(avg_f2, avg_f1)  # Bewegung aus ref
        # Projektion auf aktuellen Frame ausgehend von selektierter Position
        new_pos = (p0s[0] + proj_vec[0], p0s[1] + proj_vec[1])

        # --------------------------
        # ∎ ACTUAL UPDATE
        # --------------------------
        mk = st.markers.find_frame(f)
        if mk:
            mk.co[0] = new_pos[0]
            mk.co[1] = new_pos[1]

    return {"FINISHED"}

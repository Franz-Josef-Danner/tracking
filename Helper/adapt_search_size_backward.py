# Helper/adapt_search_size_backward.py
# ------------------------------------------------------------
# Rückwärtsversion des dynamischen Search-Size-Systems.
# Sucht Referenzmarker in F, F-1 und F-2 und verwendet deren
# Bewegung von (F-2) → (F) zur Skalierung. Pattern-Werte bleiben
# Minimum/Fallback.
#
# Search-Size = max(pattern_based, motion_based), achsenweise
# max. 200 px je Achse. pattern_based = 2 * pattern_size.
# ------------------------------------------------------------

import bpy
from mathutils import Vector


# ------------------------------------------------------------
# Reuse des gleichen Loaders & Pattern-Helpers
# ------------------------------------------------------------

def _load_calibrate_tracks(scene) -> list:
    val = scene.get("calibrate_tracks", None)
    if not val:
        return []
    if isinstance(val, (list, tuple)):
        return [str(t).strip() for t in val if isinstance(t, (str, int))]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    try:
        return [str(x).strip() for x in list(val)]
    except Exception:
        return []


def _compute_pattern_size(marker) -> Vector:
    try:
        bb = marker.pattern_bound_box
        x0, y0 = bb[0]
        x1, y1 = bb[1]
        return Vector((abs(x1 - x0), abs(y1 - y0)))
    except Exception:
        return Vector((0.0, 0.0))


def _get_marker_at_frame(track: bpy.types.MovieTrackingTrack, frame: int):
    for mk in track.markers:
        try:
            if mk.frame == frame:
                return mk
        except Exception:
            pass
    return None


def _apply_search_size(
    marker,
    pattern_size_nominal: Vector,
    clip_width: float,
    clip_height: float,
    scale_factor: float = 2.0,
    max_search_px: float = 200.0,
    motion_search_px: Vector | None = None,
):
    if clip_width <= 0.0 or clip_height <= 0.0:
        return

    pattern_px = Vector((
        pattern_size_nominal.x * float(clip_width),
        pattern_size_nominal.y * float(clip_height),
    ))

    fallback_px = pattern_px * scale_factor
    fallback_px.x = min(fallback_px.x, max_search_px)
    fallback_px.y = min(fallback_px.y, max_search_px)

    if motion_search_px is not None:
        search_px = Vector((
            max(fallback_px.x, motion_search_px.x),
            max(fallback_px.y, motion_search_px.y),
        ))
    else:
        search_px = fallback_px

    search_px.x = min(search_px.x, max_search_px)
    search_px.y = min(search_px.y, max_search_px)

    search_size_nominal = Vector((
        search_px.x / float(clip_width),
        search_px.y / float(clip_height),
    ))
    half = search_size_nominal * 0.5

    marker.search_min = Vector((-half.x, -half.y))
    marker.search_max = Vector((+half.x, +half.y))


# ------------------------------------------------------------
# Rückwärts-Funktion
# ------------------------------------------------------------

def adapt_search_size_for_calibrate_tracks_backward(context):
    """
    Search-Size für Rückwärts-Tracking. Nutzt Marker im Frame:
        F, F-1, F-2
    Bewegung = | pos(F) - pos(F-2) |
    Danach identische Behandlung wie Forward-Funktion.
    """
    scene = context.scene
    current_frame = scene.frame_current

    track_names = _load_calibrate_tracks(scene)
    if not track_names:
        return

    clip = getattr(context.space_data, "clip", None)
    if not clip or not getattr(clip, "tracking", None):
        return

    tracking = clip.tracking

    clip_width = float(clip.size[0])
    clip_height = float(clip.size[1])
    if clip_width <= 0.0 or clip_height <= 0.0:
        return

    f = current_frame
    f1 = current_frame - 1
    f2 = current_frame - 2

    # ------------------------------------------------------------
    # Referenzen sammeln (F, F-1, F-2)
    # ------------------------------------------------------------
    ref_entries = []
    for tr in tracking.tracks:
        try:
            if getattr(tr, "mute", False):
                continue
        except Exception:
            pass

        mk_f = _get_marker_at_frame(tr, f)
        mk_f1 = _get_marker_at_frame(tr, f1)
        mk_f2 = _get_marker_at_frame(tr, f2)

        if not mk_f or not mk_f1 or not mk_f2:
            continue
        if getattr(mk_f, "mute", False) or getattr(mk_f1, "mute", False) or getattr(mk_f2, "mute", False):
            continue
        if getattr(mk_f, "is_valid", True) is False or getattr(mk_f1, "is_valid", True) is False or getattr(mk_f2, "is_valid", True) is False:
            continue

        try:
            pos_f = Vector(mk_f.co)
            pos_f2 = Vector(mk_f2.co)
        except Exception:
            continue

        dist = (pos_f - pos_f2).length
        if dist <= 0.0:
            continue

        ref_entries.append({
            "track": tr,
            "pos_f": pos_f,
            "dist": dist,
        })

    has_refs = len(ref_entries) > 0

    # ------------------------------------------------------------
    # Apply auf Kalibrierungsmarker (nur Frame F)
    # ------------------------------------------------------------
    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue

        for mk in tr.markers:
            try:
                if mk.frame != current_frame:
                    continue
            except Exception:
                continue

            if getattr(mk, "mute", False):
                continue

            pattern_size = _compute_pattern_size(mk)
            if pattern_size.length == 0.0 and not has_refs:
                continue

            motion_search_px = None

            if has_refs:
                try:
                    marker_pos_f = Vector(mk.co)
                except Exception:
                    marker_pos_f = None

                if marker_pos_f is not None:
                    distances = []
                    for entry in ref_entries:
                        d = (entry["pos_f"] - marker_pos_f).length
                        distances.append((d, entry))

                    if distances:
                        distances.sort(key=lambda x: x[0])
                        nearest = [e for (_, e) in distances[:3]]
                        if nearest:
                            avg_move = sum(e["dist"] for e in nearest) / float(len(nearest))
                            if avg_move > 0.0:
                                motion_search_px = Vector((
                                    avg_move * clip_width,
                                    avg_move * clip_height,
                                ))

            _apply_search_size(
                mk,
                pattern_size_nominal=pattern_size,
                clip_width=clip_width,
                clip_height=clip_height,
                scale_factor=2.0,
                max_search_px=200.0,
                motion_search_px=motion_search_px,
            )
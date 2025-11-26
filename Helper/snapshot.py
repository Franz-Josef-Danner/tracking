# Helper/snapshot.py
# ---------------------------------------------------------------------
# Erweiterte Snapshot-Version mit persistenter UUID-Vergabe
# Kompatibel mit Marker-Kalibrierung (UUID-basiert)
# ---------------------------------------------------------------------

import bpy, uuid
from typing import List, Dict, Any, Optional
import ast

MarkerSnapshot = Dict[str, Any]


# ============================================================
# Aktive Marker im aktuellen Frame
# ============================================================
def snapshot_active_markers(context) -> List[MarkerSnapshot]:
    try:
        space = getattr(context, "space_data", None)
        clip_ui = getattr(space, "clip", None) if space else None
        clip_edit = getattr(context, "edit_movieclip", None)
        clip = clip_ui or clip_edit
        if clip is None or not getattr(clip, "tracking", None):
            return []
    except Exception:
        return []

    tracking = clip.tracking
    current_frame = int(getattr(context.scene, "frame_current", 0))
    out: List[MarkerSnapshot] = []

    for track in tracking.tracks:
        if getattr(track, "mute", False):
            continue
        marker = track.markers.find_frame(current_frame)
        if marker is None or getattr(marker, "mute", False):
            continue
        out.append({
            "track": track.name,
            "frame": int(marker.frame),
            "co": (float(marker.co[0]), float(marker.co[1])),
            "is_keyed": bool(getattr(marker, "is_keyed", False)),
        })
    return out


# ============================================================
# Hilfsfunktionen
# ============================================================
def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    clip_ui = getattr(space, "clip", None) if space else None
    clip_edit = getattr(context, "edit_movieclip", None)
    return clip_ui or clip_edit


def _ensure_uuid(track: bpy.types.MovieTrackingTrack) -> str:
    """Vergibt persistente UUID, falls noch nicht vorhanden."""
    if "kt_uid" not in track:
        track["kt_uid"] = str(uuid.uuid4())
    return track["kt_uid"]


# ============================================================
# Snapshots aller Tracks
# ============================================================
def snapshot_all_tracks(context: bpy.types.Context, *, include_muted: bool = True) -> List[Dict[str, Any]]:
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return []

    out = []
    for t in clip.tracking.tracks:
        if not include_muted and getattr(t, "mute", False):
            continue
        uid = _ensure_uuid(t)
        out.append({
            "name": t.name,
            "uuid": uid,
            "muted": bool(getattr(t, "mute", False)),
            "marker_count": len(getattr(t, "markers", [])),
        })
    return out


# ============================================================
# Store in Szene (UUID-basiert)
# ============================================================
def store_tracks_in_scene(
    scene: bpy.types.Scene,
    context: bpy.types.Context,
    key: str = "good_tracks",
    include_muted: bool = False
):
    """
    Speichert UUID + Namen + UUID→Name Map nach key.
    key kann sein: 'good_tracks', 'best_tracks', 'calibrate_tracks'
    Löscht nur eigene Keys, nicht andere Listen.
    """
    # 1) Vorhandene Keys nur selektiv löschen
    for k in (key, f"{key}_names", f"{key}_uuid_map"):
        if k in scene:
            del scene[k]

    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return

    all_tracks = list(clip.tracking.tracks)
    if not all_tracks:
        return

    uuid_map: Dict[str, str] = {}
    uuids: List[str] = []
    names: List[str] = []

    for t in all_tracks:
        if not include_muted and getattr(t, "mute", False):
            continue
        uid = _ensure_uuid(t)
        uuid_map[uid] = t.name
        uuids.append(uid)
        names.append(t.name)

    scene[key] = uuids
    scene[f"{key}_names"] = names

    try:
        scene[f"{key}_uuid_map"] = uuid_map
    except TypeError:
        scene[f"{key}_uuid_map"] = str(uuid_map)

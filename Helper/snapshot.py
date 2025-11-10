import bpy
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------
# Datentyp für Marker-Snapshots
# ---------------------------------------------------------------------
MarkerSnapshot = Dict[str, Any]

# ---------------------------------------------------------------------
# Aktive Marker im aktuellen Frame erfassen
# ---------------------------------------------------------------------
def snapshot_active_markers(context) -> List[MarkerSnapshot]:
    """Erfasst alle **aktiven** (Track nicht gemutet, Marker nicht gemutet)
    Marker im aktuellen Frame. Rückgabe:
    [{ 'track': str, 'frame': int, 'co': (x, y), 'is_keyed': bool }]
    """
    try:
        area_type = getattr(getattr(context, "area", None), "type", None)
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


# ---------------------------------------------------------------------
# Erweiterte Varianten: Tracks statt Marker
# ---------------------------------------------------------------------
def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    """Hilfsfunktion: Liefert aktiven Clip aus Clip Editor oder Edit MovieClip."""
    space = getattr(context, "space_data", None)
    clip_ui = getattr(space, "clip", None) if space else None
    clip_edit = getattr(context, "edit_movieclip", None)
    return clip_ui or clip_edit


def snapshot_all_tracks_ids(context: bpy.types.Context, *, include_muted: bool = True) -> List[str]:
    """
    Gibt **alle Track-IDs** (als Strings) des aktiven Clips zurück.
    Optional: include_muted=False, um gemutete Tracks auszuschließen.
    """
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return []

    tracks = clip.tracking.tracks
    if not include_muted:
        tracks = [t for t in tracks if not getattr(t, "mute", False)]

    return [str(id(t)) for t in tracks]


def snapshot_all_tracks_names(context: bpy.types.Context, *, include_muted: bool = True) -> List[str]:
    """
    Gibt **alle Track-Namen** des aktiven Clips zurück.
    Optional: include_muted=False, um gemutete Tracks auszuschließen.
    """
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return []

    tracks = clip.tracking.tracks
    if not include_muted:
        tracks = [t for t in tracks if not getattr(t, "mute", False)]

    return [t.name for t in tracks]


def snapshot_all_tracks(context: bpy.types.Context, *, include_muted: bool = True) -> List[Dict[str, Any]]:
    """
    Gibt eine Liste aller Tracks zurück (Name, ID, Mutestatus, Markeranzahl).
    Beispielausgabe:
    [
        { 'name': 'Track001', 'id': '1234567890', 'muted': False, 'marker_count': 24 },
        ...
    ]
    """
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        return []

    out = []
    for t in clip.tracking.tracks:
        if not include_muted and getattr(t, "mute", False):
            continue
        out.append({
            "name": t.name,
            "id": str(id(t)),
            "muted": bool(getattr(t, "mute", False)),
            "marker_count": len(getattr(t, "markers", [])),
        })
    return out


# ---------------------------------------------------------------------
# Utility-Funktion: Direkter Write in Szene
# ---------------------------------------------------------------------
def store_tracks_in_scene(scene: bpy.types.Scene, context: bpy.types.Context, key: str = "good_tracks"):
    """
    Nimmt alle Tracks des aktiven Clips und speichert deren IDs unter scene[key].
    Existierende Schlüssel 'good_tracks', 'good_track_ids', 'best_tracks'
    werden vorher gelöscht, um Konflikte zu vermeiden.
    """
    for k in ("good_tracks", "good_track_ids", "best_tracks"):
        if k in scene:
            del scene[k]

    ids = snapshot_all_tracks_ids(context)
    if not ids:
        print(f"[SNAPSHOT] Keine Tracks gefunden – scene['{key}'] bleibt leer.")
        return

    scene[key] = ids
    scene["good_track_ids"] = ids  # Alias für Rückwärtskompatibilität
    print(f"[SNAPSHOT] {len(ids)} Tracks gespeichert unter scene['{key}'].")
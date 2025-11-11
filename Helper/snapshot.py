# Helper/snapshot.py
# ---------------------------------------------------------------------
# Erweiterte Snapshot-Version mit persistenter UUID-Vergabe
# Kompatibel mit Marker-Kalibrierung (UUID-basiert)
# ---------------------------------------------------------------------

import bpy, uuid
from typing import List, Dict, Any, Optional

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
            print("[snapshot_active_markers] ❌ Kein aktiver Clip – Abbruch.")
            return []
    except Exception as e:
        print(f"[snapshot_active_markers] ❌ Kontextfehler: {e}")
        return []

    tracking = clip.tracking
    current_frame = int(getattr(context.scene, "frame_current", 0))
    out: List[MarkerSnapshot] = []
    count_skipped = 0

    for track in tracking.tracks:
        if getattr(track, "mute", False):
            count_skipped += 1
            continue
        marker = track.markers.find_frame(current_frame)
        if marker is None or getattr(marker, "mute", False):
            count_skipped += 1
            continue
        out.append({
            "track": track.name,
            "frame": int(marker.frame),
            "co": (float(marker.co[0]), float(marker.co[1])),
            "is_keyed": bool(getattr(marker, "is_keyed", False)),
        })

    print(f"[snapshot_active_markers] Frame {current_frame}: {len(out)} aktive Marker, {count_skipped} übersprungen.")
    return out


# ============================================================
# Hilfsfunktionen
# ============================================================
def _get_active_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    clip_ui = getattr(space, "clip", None) if space else None
    clip_edit = getattr(context, "edit_movieclip", None)
    clip = clip_ui or clip_edit
    if clip:
        print(f"[_get_active_clip] Aktiver Clip erkannt: {clip.name} (ID={id(clip)})")
    else:
        print("[_get_active_clip] ❌ Kein Clip im aktiven Kontext gefunden.")
    return clip


def _ensure_uuid(track: bpy.types.MovieTrackingTrack) -> str:
    """Vergibt persistente UUID, falls noch nicht vorhanden."""
    if "kt_uid" not in track:
        track["kt_uid"] = str(uuid.uuid4())
        print(f"[_ensure_uuid] Neue UUID vergeben für Track '{track.name}': {track['kt_uid']}")
    return track["kt_uid"]


# ============================================================
# Snapshots aller Tracks
# ============================================================
def snapshot_all_tracks(context: bpy.types.Context, *, include_muted: bool = True) -> List[Dict[str, Any]]:
    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        print("[snapshot_all_tracks] ❌ Kein gültiger Clip – Abbruch.")
        return []

    total = len(clip.tracking.tracks)
    muted = sum(1 for t in clip.tracking.tracks if getattr(t, "mute", False))
    print(f"[snapshot_all_tracks] Gesamttracks im Clip: {total} (gemutet: {muted})")

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

    print(f"[snapshot_all_tracks] {len(out)} Tracks in Snapshot übernommen.")
    if out:
        print(f"[snapshot_all_tracks] Beispiel: {out[0]}")
    return out


# ============================================================
# Store in Szene (UUID-basiert)
# ============================================================
def store_tracks_in_scene(scene: bpy.types.Scene, context: bpy.types.Context, key: str = "good_tracks"):
    """
    Erstellt einen vollständigen, persistenten Snapshot aller Tracks des aktiven Clips:
      - scene['good_tracks'] = [UUIDs]
      - scene['good_tracks_names'] = [Namen]
      - scene['good_tracks_uuid_map'] = "{uuid: name, ...}"
    Alte Einträge werden vorher entfernt.
    """
    print(f"\n[store_tracks_in_scene] ---- START (key='{key}') ----")
    old_keys = [k for k in scene.keys() if 'good' in k or 'best' in k]
    if old_keys:
        print(f"[store_tracks_in_scene] Vorhandene Scene-Keys vor Cleanup: {old_keys}")
    else:
        print("[store_tracks_in_scene] Keine vorhandenen Scene-Keys (good/best) vor Cleanup.")

    for k in ("good_tracks", "good_tracks_names", "good_tracks_uuid_map",
              "best_tracks", "best_tracks_names", "best_tracks_uuid_map"):
        if k in scene:
            del scene[k]
    print("[store_tracks_in_scene] Alte Scene-Keys (good/best) entfernt.")

    clip = _get_active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        print("[store_tracks_in_scene] ❌ Kein aktiver Clip gefunden – Abbruch.")
        return

    all_tracks = list(clip.tracking.tracks)
    if not all_tracks:
        print("[store_tracks_in_scene] ⚠️ Keine Tracks im Clip – Szene bleibt leer.")
        return

    # UUID-Registrierung und Mapping
    uuid_map: Dict[str, str] = {}
    uuids: List[str] = []
    names: List[str] = []
    skipped_muted = 0

    for t in all_tracks:
        if getattr(t, "mute", False):
            skipped_muted += 1
            continue
        uid = _ensure_uuid(t)
        if uid in uuid_map:
            print(f"[store_tracks_in_scene][WARN] Doppelte UUID erkannt: {uid} (Track '{t.name}')")
        uuid_map[uid] = t.name
        uuids.append(uid)
        names.append(t.name)

    scene[key] = uuids
    scene[f"{key}_names"] = names
    scene[f"{key}_uuid_map"] = str(uuid_map)

    # --- LOGGING ---
    print(f"[store_tracks_in_scene] Clip '{clip.name}' – {len(uuids)} aktive Tracks gespeichert "
          f"(+ {skipped_muted} gemutet übersprungen)")
    print(f"[store_tracks_in_scene] UUID/Namen-Map erstellt ({len(uuid_map)} Einträge)")
    if uuids:
        print(f"[store_tracks_in_scene] Beispiele UUIDs: {uuids[:5]}")
        print(f"[store_tracks_in_scene] Beispiele Namen: {names[:5]}")
    print(f"[store_tracks_in_scene] Scene Keys nach Speicherung: "
          f"{[k for k in scene.keys() if 'good' in k or 'best' in k]}")
    print("[store_tracks_in_scene] ---- ENDE ----\n")

# Helper/weak_frame_helper.py – nur aktive Marker zählen
import bpy
from typing import Dict, Optional
from .scene import get_scene_range
from .playhead_helper import reset_to_frame

def find_first_weak_frame(context: bpy.types.Context) -> Optional[int]:
    """
    Zählt **nur aktive** Marker:
      - Track ist nicht gemutet (track.mute == False)
      - Marker ist nicht gemutet (marker.mute == False)
    Sucht globales Minimum innerhalb der Szenenrange.
    """
    scene = context.scene
    target_markers = getattr(scene, "kaiserlich_markers_per_frame", None)
    if target_markers is None:
        print("❌ Szeneigenschaft 'kaiserlich_markers_per_frame' nicht gefunden.")
        return None

    clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        print("❌ Kein aktiver Movie Clip im Editor gefunden.")
        return None

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("❌ Aktiver Clip hat kein Tracking-Objekt.")
        return None

    frame_start, frame_end = get_scene_range(context)
    if frame_end < frame_start:
        print("⚠️ Ungültiger Szenenbereich.")
        return None

    markers_per_frame: Dict[int, int] = {f: 0 for f in range(frame_start, frame_end + 1)}

    # *** NUR AKTIVE MARKER ZÄHLEN ***
    for track in getattr(tracking, "tracks", []):
        if getattr(track, "mute", False):          # gemutete Tracks ignorieren
            continue
        for marker in getattr(track, "markers", []):
            if getattr(marker, "mute", False):     # gemutete Marker ignorieren
                continue
            f = int(getattr(marker, "frame", -10**9))
            if frame_start <= f <= frame_end:
                markers_per_frame[f] += 1

    if not markers_per_frame:
        print("⚠️ Keine Frames verfügbar.")
        return None

    min_count = min(markers_per_frame.values())
    if min_count >= int(target_markers):
        print(f"⚠️ Globales Minimum ist {min_count}, liegt aber nicht unter Ziel {target_markers}. Kein Treffer.")
        return None

    for f in range(frame_start, frame_end + 1):
        if markers_per_frame[f] == min_count:
            reset_to_frame(context, f)
            print(f"✅ Schwächster Frame gefunden: {f} mit {min_count} aktiven Markern (Ziel: {target_markers})")
            return f

    print("⚠️ Kein Frame trotz gültigem Minimum gefunden.")
    return None

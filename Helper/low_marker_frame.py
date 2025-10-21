import bpy

def find_first_weak_frame(context):
    """
    Findet den frühesten Frame im aktiven MovieClip mit der *geringsten* Markeranzahl (globales Minimum).
    Gate: Nur gültig, wenn diese Markeranzahl < scene.kaiserlich_markers_per_frame ist.
    Setzt bei Erfolg scene.frame_current auf den gefundenen Frame und gibt ihn zurück.
    Gibt None zurück, falls kein Frame das Gate erfüllt oder kein aktiver Clip vorhanden ist.
    """
    scene = context.scene
    target_markers = getattr(scene, "kaiserlich_markers_per_frame", None)
    if target_markers is None:
        print("❌ Szeneigenschaft 'kaiserlich_markers_per_frame' nicht gefunden.")
        return None

    # Aktiven Clip ermitteln (Clip Editor vorausgesetzt)
    space_data = getattr(context, "space_data", None)
    clip = getattr(space_data, "clip", None) if space_data else None
    if not clip:
        print("❌ Kein aktiver Movie Clip im Editor gefunden.")
        return None

    tracking = clip.tracking

    # Framebereich bestimmen (vollständige Timeline des Clips)
    frame_start = int(getattr(clip, "frame_start", scene.frame_start))
    frame_duration = int(getattr(clip, "frame_duration", 0))
    if frame_duration <= 0:
        # Fallback: Szene nutzen
        frame_start = scene.frame_start
        frame_end = scene.frame_end
    else:
        frame_end = frame_start + frame_duration - 1

    if frame_end < frame_start:
        print("⚠️ Ungültiger Framebereich.")
        return None

    # Markeranzahl pro Frame initialisieren (inkl. Frames mit 0 Markern)
    markers_per_frame = {f: 0 for f in range(frame_start, frame_end + 1)}

    # Zählen aller Marker über alle Tracks
    # (Optional: nur aktive/unsichtbare/mute-Filter einbauen, wenn gewünscht)
    for track in tracking.tracks:
        # Falls stummgeschaltete/gesperrte Tracks ignoriert werden sollen:
        # if getattr(track, "mute", False) or getattr(track, "lock", False):
        #     continue
        for marker in track.markers:
            f = int(marker.frame)
            if frame_start <= f <= frame_end:
                markers_per_frame[f] += 1

    # Globales Minimum bestimmen
    min_count = min(markers_per_frame.values()) if markers_per_frame else None
    if min_count is None:
        print("⚠️ Keine Frames verfügbar.")
        return None

    # Gate prüfen: Minimum muss kleiner als Ziel sein
    if min_count >= target_markers:
        print(f"⚠️ Globales Minimum ist {min_count}, liegt aber nicht unter Ziel {target_markers}. Kein Treffer.")
        return None

    # Frühesten Frame mit diesem Minimum nehmen
    for f in range(frame_start, frame_end + 1):
        if markers_per_frame[f] == min_count:
            scene.frame_current = f
            print(f"✅ Schwächster Frame gefunden: {f} mit {min_count} Markern (Ziel: {target_markers})")
            return f

    # Sollte praktisch nie erreicht werden
    print("⚠️ Kein Frame trotz gültigem Minimum gefunden.")
    return None

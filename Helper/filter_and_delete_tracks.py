import bpy

def filter_and_delete_tracks(
    include_names=None,
    exclude_names=None,
    threshold=50.0,
    clip=None
):
    """
    Führt `bpy.ops.clip.filter_tracks()` mit angegebenem Threshold aus
    und löscht anschließend gezielt Tracks nach Namensfilterung.

    Args:
        include_names (list[str]): Nur diese Tracknamen verarbeiten (Whitelist).
        exclude_names (list[str]): Diese Tracknamen ausschließen (Blacklist).
        threshold (float): Threshold für Filteroperation.
        clip (MovieClip): Optional ein bestimmter Clip (Standard = aktiver Clip).
    """

    # --- Clip-Kontext absichern ---
    if clip is None:
        clip = bpy.context.edit_movieclip
    if clip is None:
        print("[Helper][FilterDelete] ❌ Kein aktiver Clip gefunden.")
        return

    tracking = clip.tracking
    tracks = tracking.tracks

    # --- Auswahl resetten ---
    for t in tracks:
        t.select = False

    # --- Tracks nach Name filtern ---
    selected = []
    for track in tracks:
        name = track.name

        # Whitelist-Filter
        if include_names and name not in include_names:
            continue

        # Blacklist-Filter
        if exclude_names and name in exclude_names:
            continue

        track.select = True
        selected.append(name)

    if not selected:
        print("[Helper][FilterDelete] ⚠️ Keine Tracks für Filter/Delete ausgewählt.")
        return

    print(f"[Helper][FilterDelete] ▶️ {len(selected)} Tracks selektiert: {selected}")

    # --- Sicherstellen, dass im richtigen Kontext gearbeitet wird ---
    area = None
    for a in bpy.context.screen.areas:
        if a.type == "CLIP_EDITOR":
            area = a
            break

    if area is None:
        print("[Helper][FilterDelete] ❌ Kein Movie Clip Editor aktiv.")
        return

    # --- Operatoren ausführen ---
    with bpy.context.temp_override(area=area, edit_movieclip=clip):
        try:
            bpy.ops.clip.filter_tracks(threshold=threshold)
            print(f"[Helper][FilterDelete] ✅ Filter mit threshold={threshold} ausgeführt.")
        except Exception as e:
            print(f"[Helper][FilterDelete] ❌ Fehler bei filter_tracks(): {e}")

        try:
            bpy.ops.clip.delete_track()
            print("[Helper][FilterDelete] 🗑️ Selektierte Tracks gelöscht.")
        except Exception as e:
            print(f"[Helper][FilterDelete] ❌ Fehler bei delete_track(): {e}")

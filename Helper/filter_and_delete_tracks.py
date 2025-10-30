import bpy

def filter_and_delete_tracks(
    include_names=None,
    exclude_names=None,
    track_threshold=30.0,
    clip=None
):
    """
    Führt `bpy.ops.clip.filter_tracks()` mit angegebenem Threshold aus
    und löscht anschließend **nur die tatsächlich vom Filter betroffenen Tracks**.

    Args:
        include_names (list[str]): Nur diese Tracknamen verarbeiten (Whitelist).
        exclude_names (list[str]): Diese Tracknamen ausschließen (Blacklist).
        track_threshold (float): Threshold für Filteroperation (Blender: track_threshold).
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

    # --- Auswahl vorbereiten ---
    for t in tracks:
        t.select = False

    # --- Selektionslogik anwenden ---
    selected_for_filter = []
    for track in tracks:
        name = track.name
        if include_names and name not in include_names:
            continue
        if exclude_names and name in exclude_names:
            continue
        track.select = True
        selected_for_filter.append(name)

    if not selected_for_filter:
        print("[Helper][FilterDelete] ⚠️ Keine Tracks zur Filterung ausgewählt.")
        return

    print(f"[Helper][FilterDelete] ▶️ {len(selected_for_filter)} Tracks für Filter ausgewählt.")

    # --- Movie-Clip-Editor Kontext ---
    area = None
    for a in bpy.context.screen.areas:
        if a.type == "CLIP_EDITOR":
            area = a
            break

    if area is None:
        print("[Helper][FilterDelete] ❌ Kein Movie Clip Editor aktiv.")
        return

    # --- Filter anwenden ---
    with bpy.context.temp_override(area=area, edit_movieclip=clip):
        try:
            bpy.ops.clip.filter_tracks(track_threshold=track_threshold)
            print(f"[Helper][FilterDelete] ✅ Filter ausgeführt (track_threshold={track_threshold})")
        except Exception as e:
            print(f"[Helper][FilterDelete] ❌ Fehler bei filter_tracks(): {e}")
            return

        # --- Nach dem Filter: erfassen, welche Tracks tatsächlich selektiert blieben ---
        filtered_names = [t.name for t in tracks if t.select]
        if not filtered_names:
            print("[Helper][FilterDelete] ⚠️ Kein Track vom Filter betroffen — kein Delete.")
            return

        print(f"[Helper][FilterDelete] 🔸 {len(filtered_names)} Tracks werden gelöscht: {filtered_names[:5]}{' …' if len(filtered_names) > 5 else ''}")

        # --- Nur die selektierten (gefilterten) löschen ---
        try:
            bpy.ops.clip.delete_track()
            print(f"[Helper][FilterDelete] 🗑️ {len(filtered_names)} Tracks gelöscht.")
        except Exception as e:
            print(f"[Helper][FilterDelete] ❌ Fehler bei delete_track(): {e}")

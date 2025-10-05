import bpy

def apply_marker_sizes(clip, pz: int, sz: int):
    """Setzt die Standard Pattern/Search Größe für neue Tracks.
    Verwendet die Tracking Settings des aktiven Movie Clips.
    """
    if clip is None:
        print("[Kaiserlich Tracker] Kein Clip übergeben – Abbruch.")
        return

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("[Kaiserlich Tracker] Clip besitzt kein tracking-Attribut – API Änderung?")
        return

    settings = getattr(tracking, "settings", None)
    if settings is None:
        print("[Kaiserlich Tracker] tracking.settings nicht verfügbar – Abbruch.")
        return

    # Blender verwendet pattern_size und search_size (Kantenlänge in Pixeln)
    settings.default_pattern_size = pz
    settings.default_search_size = sz

    print(f"[Kaiserlich Tracker] default_pattern_size auf {pz} gesetzt")
    print(f"[Kaiserlich Tracker] default_search_size auf {sz} gesetzt")

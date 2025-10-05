import bpy

def apply_marker_sizes(pz: int, sz: int):
    """Setzt die Standard Pattern/Search Größe für neue Tracks.
    In Blender sind dies die Preferences für Tracking (Movie Clip Editor -> Track-Einstellungen).
    """
    # Die Eigenschaften existieren pro Szene als Tracking-Settings
    scene = bpy.context.scene
    tracking_settings = scene.tracking.settings

    # Blender verwendet pattern_size und search_size (Quadrat-Kantenlänge in Pixeln)
    tracking_settings.default_pattern_size = pz
    tracking_settings.default_search_size = sz

    print(f"[Kaiserlich Tracker] default_pattern_size auf {pz} gesetzt")
    print(f"[Kaiserlich Tracker] default_search_size auf {sz} gesetzt")

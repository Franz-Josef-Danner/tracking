import bpy

def apply_marker_sizes(context, pz: int, sz: int):
    """Setzt Default- und (Fallback) aktuelle Pattern- und Search-Size für neue Tracks.

    Parameter:
      pz (int): pattern size
      sz (int): search size
    """
    space = getattr(context, 'space_data', None)
    if not (space and getattr(space, 'type', None) == 'CLIP_EDITOR'):
        print("[Kaiserlich Tracker] apply_marker_sizes: Kein Clip Editor Kontext.")
        return False

    clip = getattr(space, 'clip', None)
    if not clip:
        print("[Kaiserlich Tracker] apply_marker_sizes: Kein aktiver Clip.")
        return False

    tracking = clip.tracking
    try:
        settings = tracking.settings
        changed = False
        if hasattr(settings, 'default_pattern_size'):
            settings.default_pattern_size = int(pz)
            changed = True
        if hasattr(settings, 'default_search_size'):
            settings.default_search_size = int(sz)
            changed = True
        # Fallback für einige Blender-Versionen
        if hasattr(settings, 'pattern_size'):
            settings.pattern_size = int(pz)
            changed = True
        if hasattr(settings, 'search_size'):
            settings.search_size = int(sz)
            changed = True
        if changed:
            print(f"[Kaiserlich Tracker] Marker sizes gesetzt: pattern={int(pz)} search={int(sz)}")
        else:
            print("[Kaiserlich Tracker] Konnte keine Marker Size Properties finden.")
        return changed
    except Exception as e:
        print(f"[Kaiserlich Tracker] Fehler beim Setzen der Marker Sizes: {e}")
        return False

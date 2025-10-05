import bpy

def apply(pz: int, sz: int):
    """Setzt Default Pattern & Search Size für neue Marker im aktiven Clip."""
    clip = bpy.context.edit_movieclip
    if not clip:
        print('Kein Clip für marker_size.apply()')
        return
    try:
        settings = clip.tracking.settings
        # Blender erwartet typische Größen im Bereich 4..128 – wir setzen direkt unsere berechneten Werte.
        settings.default_pattern_size = int(pz)
        settings.default_search_size = int(sz)
        print(f'Marker Size gesetzt -> pattern: {pz}  search: {sz}')
    except Exception as e:
        print(f'Fehler beim Setzen der Marker Sizes: {e}')

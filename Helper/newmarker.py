import bpy

def run(context, values: dict, clip=None):
    """Platzhalter für Logik zum Anlegen neuer Marker falls nötig."""
    if clip is None:
        clip = getattr(bpy.context, 'edit_movieclip', None)
    if not clip:
        print('newmarker: kein Clip (Kontext ohne edit_movieclip)')
        return
    print('newmarker: Vorbereitung abgeschlossen (keine expliziten Marker erzeugt)')
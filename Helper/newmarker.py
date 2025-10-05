import bpy

def run(context, values: dict):
    """Platzhalter für Logik zum Anlegen neuer Marker falls nötig."""
    clip = bpy.context.edit_movieclip
    if not clip:
        print('newmarker: kein Clip')
        return
    # Hier könnte man gezielt Marker hinzufügen – aktuell nur Ausgabe.
    print('newmarker: Vorbereitung abgeschlossen (keine expliziten Marker erzeugt)')
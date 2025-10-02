import bpy
from math import fabs

def cleanup_new_markers(neue_marker, alte_marker, hz, vc, md):
    """
    Entfernt neue Marker die näher als md Pixel an einem alten Marker liegen.

    neue_marker / alte_marker: Liste von (track, marker)
    md: Mindestabstand in Pixeln
    hz/vc: Auflösung für Umrechnung Normal->Pixel
    Rückgabe: (bereinigte_liste, entfernte_marker_liste)
    """
    alte_pos = []
    for track, marker in alte_marker:
        x = marker.co[0] * hz
        y = marker.co[1] * vc
        alte_pos.append((x, y))

    cleaned = []
    removed = []
    for track, marker in neue_marker:
        x = marker.co[0] * hz
        y = marker.co[1] * vc
        zu_nahe = False
        for ax, ay in alte_pos:
            # Pseudocode: wenn disH < md ODER disV < md -> löschen
            if abs(ax - x) < md or abs(ay - y) < md:
                zu_nahe = True
                break
        if zu_nahe:
            removed.append((track, marker))
        else:
            cleaned.append((track, marker))
    return cleaned, removed

"""Bereinigt neu erzeugte Marker / Tracks, die zu nahe an bestehenden alten Markern liegen.

Eingangsdaten basieren auf den Snapshot-Dictionaries aus snapshot_active_markers:
  { 'track': str, 'frame': int, 'co': (x_norm, y_norm), 'is_keyed': bool }

Algorithmus (aus Anforderung):
  Für jeden neuen Marker nm vergleiche mit allen alten Markern ama:
    amahpo = ama.co.x * hz (Pixel X)
    amavpo = ama.co.y * vc (Pixel Y)
    nmhpo  = nm.co.x  * hz
    nmvpo  = nm.co.y  * vc
    disH = abs(amahpo - nmhpo)
    disV = abs(amavpo - nmvpo)
    Wenn disH < md -> Track des neuen Markers löschen
    Sonst wenn disV < md -> Track des neuen Markers löschen
    Sonst behalten

Rückgabe: (liste_gehaltene_neue_marker, anzahl_geloescht)
"""
from typing import List, Dict, Any, Tuple
from .delete import delete_track_by_name

MarkerSnapshot = Dict[str, Any]

def cleanup_new_markers(context, alte_marker: List[MarkerSnapshot], neue_marker: List[MarkerSnapshot], *, md: float, hz: int, vc: int) -> Tuple[List[MarkerSnapshot], int]:
    if not neue_marker:
        return [], 0

    kept: List[MarkerSnapshot] = []
    deleted_count = 0

    # Für Effizienz Pixel-Koordinaten der alten Marker vorberechnen
    alte_pixels = [ (m, m['co'][0]*hz, m['co'][1]*vc) for m in alte_marker ]

    for nm in neue_marker:
        nm_px_x = nm['co'][0] * hz
        nm_px_y = nm['co'][1] * vc
        should_delete = False
        for _ama, ama_px_x, ama_px_y in alte_pixels:
            disH = abs(ama_px_x - nm_px_x)
            if disH < md:  # Erst horizontal laut Vorgabe
                should_delete = True
                break
            disV = abs(ama_px_y - nm_px_y)
            if disV < md:  # Dann vertikal
                should_delete = True
                break
        if should_delete:
            if delete_track_by_name(context, nm['track']):
                deleted_count += 1
            else:
                # Löschen fehlgeschlagen -> Marker behalten, damit kein logischer Verlust entsteht
                kept.append(nm)
        else:
            kept.append(nm)

    print(f"[Kaiserlich Tracker] cleanup: {deleted_count} neue Tracks entfernt (Schwelle md={md}). Verbleibend: {len(kept)}")
    return kept, deleted_count

from typing import List, Dict, Any, Tuple

# Diese Datei verarbeitet Differenzen zweier Marker-Snapshots
# Erwartet Datenstruktur wie in snapshot.snapshot_active_markers

MarkerSnapshot = Dict[str, Any]

def diff_markers(old: List[MarkerSnapshot], new: List[MarkerSnapshot]) -> List[MarkerSnapshot]:
    """Ermittelt Marker aus 'new', die nicht in 'old' enthalten waren.
    Vergleichsbasis: Kombination aus Track-Namen und Frame.
    (Abwärtskompatible Helper-Funktion)
    """
    old_index = {(m['track'], m['frame']) for m in old}
    result = [m for m in new if (m['track'], m['frame']) not in old_index]
    print(f"[Kaiserlich Tracker] newmarker: {len(result)} neue Marker identifiziert.")
    return result

def classify_markers(old: List[MarkerSnapshot], new: List[MarkerSnapshot]) -> Tuple[List[MarkerSnapshot], List[MarkerSnapshot]]:
    """Klassifiziert die Marker der neuen Liste in (alte_vorhandene, neue_marker).

    Ein Marker gilt als 'alter Marker', wenn ein Eintrag mit gleicher (track, frame)
    bereits in 'old' enthalten war. Andernfalls ist es ein neu erzeugter Marker.

    Rückgabe: (alte_marker, neue_marker)
    """
    old_index = {(m['track'], m['frame']) for m in old}
    alte_marker = []
    neue_marker = []
    for m in new:
        if (m['track'], m['frame']) in old_index:
            alte_marker.append(m)
        else:
            neue_marker.append(m)
    print(f"[Kaiserlich Tracker] classify: {len(alte_marker)} alte / {len(neue_marker)} neue Marker")
    return alte_marker, neue_marker

from typing import List, Dict, Any

# Diese Datei verarbeitet Differenzen zweier Marker-Snapshots
# Erwartet Datenstruktur wie in snapshot.snapshot_active_markers

MarkerSnapshot = Dict[str, Any]

def diff_markers(old: List[MarkerSnapshot], new: List[MarkerSnapshot]) -> List[MarkerSnapshot]:
    """Ermittelt Marker aus 'new', die nicht in 'old' enthalten waren.
    Vergleichsbasis: Kombination aus Track-Namen und Frame.
    """
    old_index = {(m['track'], m['frame']) for m in old}
    result = [m for m in new if (m['track'], m['frame']) not in old_index]
    print(f"[Kaiserlich Tracker] newmarker: {len(result)} neue Marker identifiziert.")
    return result

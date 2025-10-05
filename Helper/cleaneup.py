import bpy
from typing import List, Tuple
from . import delete

# Struktur für differenzierte Marker-Paare (alter vs neuer)
class MarkerPair:
    def __init__(self, track_name: str, old_co: Tuple[float, float], new_co: Tuple[float, float]):
        self.track_name = track_name
        self.old_co = old_co  # (x,y) normalisiert
        self.new_co = new_co  # (x,y) normalisiert

    def distance_px(self, hz: int, vc: int):
        # Umrechnung in Pixel
        ox = self.old_co[0] * hz
        oy = self.old_co[1] * vc
        nx = self.new_co[0] * hz
        ny = self.new_co[1] * vc
        return abs(ox - nx), abs(oy - ny)


def cleanup_markers(context, marker_pairs: List[MarkerPair], md: int, hz: int, vc: int) -> int:
    """Prüft Abstände zwischen alten und neuen Markern und löscht neue Marker,
    wenn horizontal oder vertikal innerhalb md Pixel.

    Args:
        marker_pairs: Liste der Paare (alter vs neuer Marker)
        md: min_distance in Pixel
        hz: horizontale Auflösung
        vc: vertikale Auflösung

    Returns:
        int: Anzahl gelöschter neuer Marker (Tracks)
    """
    deleted = 0
    for pair in marker_pairs:
        dis_h, dis_v = pair.distance_px(hz, vc)
        if dis_h < md or dis_v < md:
            # Lösche Marker im aktuellen Frame (anstelle ganzen Tracks)
            frame_current = context.scene.frame_current
            if delete.delete_marker_frame(context, pair.track_name, frame_current):
                deleted += 1
                print(f"[Kaiserlich Tracker] Cleanup: Marker {pair.track_name}@{frame_current} gelöscht (dis_h={dis_h:.2f}, dis_v={dis_v:.2f} < md={md})")
            else:
                print(f"[Kaiserlich Tracker] Cleanup: Marker {pair.track_name}@{frame_current} konnte nicht gelöscht werden.")
        else:
            print(f"[Kaiserlich Tracker] Cleanup: Track {pair.track_name} behalten (dis_h={dis_h:.2f}, dis_v={dis_v:.2f} >= md={md})")
    print(f"[Kaiserlich Tracker] Cleanup abgeschlossen. Gelöscht: {deleted}")
    return deleted

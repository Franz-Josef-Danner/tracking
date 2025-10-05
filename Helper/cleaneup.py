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
    total = len(marker_pairs)
    # Immer Log – auch wenn keine Paare vorhanden
    print(f"[KT][cleanup] start pairs={total} md={md}")
    for idx, pair in enumerate(marker_pairs):
        dis_h, dis_v = pair.distance_px(hz, vc)
        close = (dis_h < md or dis_v < md)
        print(f"[KT][cleanup] pair#{idx} track={pair.track_name} dx={dis_h:.1f} dy={dis_v:.1f} md={md} close={close}")
        if close:
            frame_current = context.scene.frame_current
            if delete.delete_marker_frame(context, pair.track_name, frame_current):
                deleted += 1
                print(f"[KT][cleanup] deleted {pair.track_name}@{frame_current}")
    print(f"[KT][cleanup] done deleted={deleted}/{total}")
    return deleted


def delete_new_markers_close_to_old(context, old_markers, new_markers, md: int, hz: int, vc: int) -> int:
    """Vergleicht alle neuen Marker mit allen alten Markern und löscht neue Marker,
    die einem alten näher als md Pixel (horizontal ODER vertikal) kommen.

    Erwartete Struktur von old_markers/new_markers: Objekte mit Attributen
      - track_name
      - co_x, co_y (normalisierte Koordinaten 0..1)

    Args:
        context: Blender Kontext
        old_markers: Liste MarkerSnapshots vor detect
        new_markers: Liste MarkerSnapshots nach detect
        md: Mindestabstand in Pixel
        hz: horizontale Auflösung
        vc: vertikale Auflösung

    Returns:
        int: Anzahl gelöschter neuer Marker
    """
    if not new_markers:
        print(f"[KT][prox] no_new md={md}")
        return 0
    if not old_markers:
        print(f"[KT][prox] no_old new={len(new_markers)} md={md}")
        return 0

    deleted = 0
    frame_current = context.scene.frame_current
    print(f"[KT][prox] start old={len(old_markers)} new={len(new_markers)} md={md}")
    olds = [(om.track_name, om.co_x, om.co_y) for om in old_markers]

    for nm in new_markers:
        nx = nm.co_x
        ny = nm.co_y
        removed_here = False
        for (ot_name, ox, oy) in olds:
            dx = abs(nx - ox) * hz
            dy = abs(ny - oy) * vc
            if (dx < md) or (dy < md):
                if delete.delete_marker_frame(context, nm.track_name, frame_current):
                    deleted += 1
                    removed_here = True
                    print(f"[KT][prox] deleted new={nm.track_name} near_old={ot_name} dx={dx:.1f} dy={dy:.1f} md={md}")
                else:
                    print(f"[KT][prox][warn] failed_delete new={nm.track_name} near_old={ot_name} dx={dx:.1f} dy={dy:.1f}")
                break
        if not removed_here:
            print(f"[KT][prox] keep new={nm.track_name}")

    print(f"[KT][prox] done deleted={deleted}/{len(new_markers)}")
    return deleted

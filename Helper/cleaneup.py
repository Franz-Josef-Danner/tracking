"""Bereinigt alte Marker, die zu nahe an neuen Markern liegen (invertierte Logik).

Neue Vorgabe laut User (vereinfacht):
    Für jeden neuen Marker (nm) und jeden alten Marker (ama):
        Pixelkoordinaten bilden:
            amahpo_i = ama.x_norm * hz
            amavpo_i = ama.y_norm * vc
            nmhpo_i  = nm.x_norm  * hz
            nmvpo_i  = nm.y_norm  * vc
            disH_i = abs(amahpo_i - nmhpo_i)
            disV_i = abs(amavpo_i - nmvpo_i)
        Wenn disH_i < md -> lösche ama (alter Track)
        Sonst falls disV_i < md -> lösche ama
        Sonst (kein Löschen für dieses Paar)

Wichtig: Anders als die vorherige Version werden NICHT die neuen Marker gelöscht, sondern die alten, die zu nahe liegen.

Rückgabe: (liste_neuer_marker_unverändert, anzahl_geloeschter_alter_tracks)
    Die neuen Marker werden unverändert durchgereicht; der zweite Wert gibt an wie viele alte Tracks gelöscht wurden.
"""
from typing import List, Dict, Any, Tuple
from .delete import delete_track_by_name

MarkerSnapshot = Dict[str, Any]

def cleanup_new_markers(context, alte_marker: List[MarkerSnapshot], neue_marker: List[MarkerSnapshot], *, pz: int, hz: int, vc: int) -> Tuple[List[MarkerSnapshot], int]:
    """Löscht alte Tracks, die zu nahe an neuen liegen – jetzt mit pz (Pattern-Größe) als Schwelle.

    Änderung: Statt der früheren Distanzschwelle 'md' wird die Pattern-Größe 'pz' (in Pixeln) als
    Vergleichswert verwendet. Damit koppeln wir die Bereinigung an die aktuell verwendete
    Pattern-Größe.

    Kriterium (wie vorher, ODER-Logik beibehalten):
        |dx| < pz  ODER  |dy| < pz  => alter Track wird gelöscht

    Rückgabe:
        (neue_marker_unverändert, anzahl_gelöschter_alter_tracks)
    """
    if not neue_marker or not alte_marker:
        return neue_marker, 0

    # Sicherstellen, dass pz positiv ist
    if pz <= 0:
        print(f"[Kaiserlich Tracker] cleanup: Ungültiges pz={pz} -> kein Cleanup.")
        return neue_marker, 0

    deleted_old = 0
    remaining_old = {(m['track'], m['frame']): m for m in alte_marker}

    def build_old_pixel_map():
        return [(key, m['co'][0] * hz, m['co'][1] * vc, m) for key, m in remaining_old.items()]

    old_pixels = build_old_pixel_map()

    thresh = float(pz)  # als float für Formatierung

    for nm in neue_marker:
        nm_px_x = nm['co'][0] * hz
        nm_px_y = nm['co'][1] * vc
        for key, ama_px_x, ama_px_y, ama_m in list(old_pixels):
            disH = abs(ama_px_x - nm_px_x)
            if disH < thresh:
                if delete_track_by_name(context, ama_m['track']):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    print(f"[Kaiserlich Tracker] cleanup: Alter Track '{ama_m['track']}' gelöscht (disH={disH:.2f} < pz={thresh}).")
                old_pixels = build_old_pixel_map()
                continue
            disV = abs(ama_px_y - nm_px_y)
            if disV < thresh:
                if delete_track_by_name(context, ama_m['track']):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    print(f"[Kaiserlich Tracker] cleanup: Alter Track '{ama_m['track']}' gelöscht (disV={disV:.2f} < pz={thresh}).")
                old_pixels = build_old_pixel_map()
                continue

    print(f"[Kaiserlich Tracker] cleanup: {deleted_old} alte Tracks entfernt (Schwelle pz={thresh}). Neue Marker behalten: {len(neue_marker)}")
    return neue_marker, deleted_old

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

def cleanup_new_markers(context, alte_marker: List[MarkerSnapshot], neue_marker: List[MarkerSnapshot], *, md: float, hz: int, vc: int) -> Tuple[List[MarkerSnapshot], int]:
    """Löscht alte Tracks, die zu nahe (horizontal oder vertikal) an neuen liegen.

    Parameter bleiben kompatibel zur alten Signatur.
    """
    if not neue_marker or not alte_marker:
        # Nichts zu bereinigen – gebe neue Marker unverändert zurück, 0 alte gelöscht
        return neue_marker, 0

    deleted_old = 0

    # Wir arbeiten auf einer lokalen Kopie der alten Marker-Liste (für Logging optional)
    # (Aktuell nicht zurückgegeben, da Aufrufer nur neue Marker möchte)
    remaining_old = { (m['track'], m['frame']): m for m in alte_marker }

    # Für Effizienz: Precompute Koordinaten der alten Marker (wird dynamisch aktualisiert falls gelöscht)
    def build_old_pixel_map():
        return [ (key, m['co'][0]*hz, m['co'][1]*vc, m) for key, m in remaining_old.items() ]

    old_pixels = build_old_pixel_map()

    for nm in neue_marker:
        nm_px_x = nm['co'][0] * hz
        nm_px_y = nm['co'][1] * vc
        # Für jeden alten Marker prüfen
        # Da wir während Iterationen löschen können, nutzen wir eine Kopie der Strukturen
        for key, ama_px_x, ama_px_y, ama_m in list(old_pixels):
            disH = abs(ama_px_x - nm_px_x)
            if disH < md:
                # Lösche alten Track
                if delete_track_by_name(context, ama_m['track']):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    print(f"[Kaiserlich Tracker] cleanup: Alter Track '{ama_m['track']}' gelöscht (disH={disH:.2f} < md={md}).")
                # Pixel-Mapping neu aufbauen nach Löschung
                old_pixels = build_old_pixel_map()
                continue  # Weiter prüfen ob weitere alte zu nahe sind
            disV = abs(ama_px_y - nm_px_y)
            if disV < md:
                if delete_track_by_name(context, ama_m['track']):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    print(f"[Kaiserlich Tracker] cleanup: Alter Track '{ama_m['track']}' gelöscht (disV={disV:.2f} < md={md}).")
                old_pixels = build_old_pixel_map()
                continue
        # Ende Prüfung für diesen neuen Marker – neue Marker werden NIE gelöscht

    print(f"[Kaiserlich Tracker] cleanup: {deleted_old} alte Tracks entfernt (Schwelle md={md}). Neue Marker behalten: {len(neue_marker)}")
    return neue_marker, deleted_old

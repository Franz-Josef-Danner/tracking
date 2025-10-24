from typing import List, Dict, Any, Tuple
import bpy
from .delete import delete_track_by_name

MarkerSnapshot = Dict[str, Any]

def cleanup_new_markers(
    context,
    alte_marker: List[MarkerSnapshot],
    neue_marker: List[MarkerSnapshot],
    *,
    pz: int,
    hz: int,
    vc: int
) -> Tuple[List[MarkerSnapshot], int]:

    print(f"[Cleanup] Eingabe: {len(alte_marker)} alte / {len(neue_marker)} neue Marker")
    if not neue_marker or not alte_marker:
        print("[Cleanup] ❌ Keine Marker zum Bereinigen vorhanden.")
        return neue_marker, 0

    if pz <= 0:
        print("[Cleanup] ⚠️ Parameter pz <= 0 – Cleanup übersprungen.")
        return neue_marker, 0

    # Tracking referenzieren
    space = getattr(context, "space_data", None)
    clip = getattr(space, "clip", None) if space else None
    tracking = getattr(clip, "tracking", None) if clip else None

    def _track_active(name: str) -> bool:
        if not tracking:
            return False
        tr = tracking.tracks.get(name)
        return bool(tr and not getattr(tr, "mute", False))

    active_old = [m for m in alte_marker if _track_active(m["track"])]
    active_new = [m for m in neue_marker if _track_active(m["track"])]

    print(f"[Cleanup] Aktive alte Marker: {len(active_old)}")
    print(f"[Cleanup] Aktive neue Marker: {len(active_new)}")

    if not active_new or not active_old:
        print("[Cleanup] ⚠️ Keine aktiven neuen oder alten Marker – Cleanup abgebrochen.")
        return neue_marker, 0

    deleted_old = 0
    remaining_old = {(m["track"], m["frame"]): m for m in active_old}

    def build_old_pixel_map():
        # Normierte Koordinaten -> Pixel
        return [
            (key, m["co"][0] * hz, m["co"][1] * vc, m)
            for key, m in remaining_old.items()
        ]

    old_pixels = build_old_pixel_map()
    thresh = float(pz) * 0.025
    print(f"[Cleanup] Threshold: {thresh:.3f} px (basierend auf pz={pz})")

    for nm in active_new:
        nm_px_x = float(nm["co"][0]) * hz
        nm_px_y = float(nm["co"][1]) * vc

        for key, ama_px_x, ama_px_y, ama_m in list(old_pixels):
            dx = abs(ama_px_x - nm_px_x)
            dy = abs(ama_px_y - nm_px_y)

            if dx < thresh or dy < thresh:
                print(
                    f"[Cleanup][DEL] Alter Track '{ama_m['track']}' "
                    f"entfernt wegen Nähe zu neuem '{nm['track']}' "
                    f"(dx={dx:.2f}, dy={dy:.2f})"
                )
                if delete_track_by_name(context, ama_m["track"]):
                    deleted_old += 1
                    remaining_old.pop(key, None)
                    old_pixels = build_old_pixel_map()
                else:
                    print(f"[Cleanup][WARN] Löschung von '{ama_m['track']}' fehlgeschlagen.")
                break  # nur ein Treffer pro neuem Marker prüfen

    print(f"[Cleanup] Ergebnis: {deleted_old} alte Marker gelöscht, {len(neue_marker)} neue behalten.")
    return neue_marker, deleted_old

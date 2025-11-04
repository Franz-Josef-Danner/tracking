# Helper/snapshot.py
import bpy
from typing import List, Dict, Any

# Datentyp für einen einfachen Marker-Snapshot
MarkerSnapshot = Dict[str, Any]


def snapshot_active_markers(context) -> List[MarkerSnapshot]:
    """Erfasst alle **aktiven** (Track nicht gemutet, Marker nicht gemutet)
    Marker im aktuellen Frame. Rückgabe:
    { 'track': str, 'frame': int, 'co': (x, y), 'is_keyed': bool }
    Mit erweiterten Diagnose-Logs zur Kontext- und Markeranalyse.
    """

    # --- Kontextdiagnostik ---------------------------------------------------
    try:
        area_type = getattr(getattr(context, "area", None), "type", None)
        space = getattr(context, "space_data", None)
        has_space = space is not None
        space_type = getattr(space, "type", None) if has_space else None
        clip_ui = getattr(space, "clip", None) if has_space else None
        clip_edit = getattr(context, "edit_movieclip", None)
        clip = clip_ui or clip_edit

        print(
            f"[Snapshot][Diag] area={area_type}, space_type={space_type}, "
            f"has_space={has_space}, clip_ui={'Y' if clip_ui else 'N'}, "
            f"clip_edit={'Y' if clip_edit else 'N'}"
        )

        if clip is None:
            print("[Snapshot] ❌ Kein aktiver Clip im Kontext (weder space.clip noch edit_movieclip).")
            return []
    except Exception as e:
        print(f"[Snapshot][Err] Kontextabfrage fehlgeschlagen: {e!r}")
        return []

    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        print("[Snapshot] ❌ clip.tracking ist None.")
        return []

    current_frame = int(getattr(context.scene, "frame_current", 0))
    total_tracks = len(getattr(tracking, "tracks", []))
    print(f"[Snapshot][Diag] frame={current_frame}, total_tracks={total_tracks}")

    out: List[MarkerSnapshot] = []
    empty_or_muted_tracks = 0
    no_marker_at_frame = 0
    muted_markers = 0

    # --- Track-Iteration -----------------------------------------------------
    for track in tracking.tracks:
        # Nur **aktive** Tracks berücksichtigen
        if getattr(track, "mute", False):
            empty_or_muted_tracks += 1
            continue

        marker = track.markers.find_frame(current_frame)
        if marker is None:
            no_marker_at_frame += 1
            continue

        # Nur **aktive** Marker berücksichtigen
        if getattr(marker, "mute", False):
            muted_markers += 1
            continue

        out.append({
            "track": track.name,
            "frame": int(marker.frame),
            "co": (float(marker.co[0]), float(marker.co[1])),
            "is_keyed": bool(getattr(marker, "is_keyed", False)),
        })

    # --- Ergebnisdiagnostik --------------------------------------------------
    if not out:
        print(
            "[Snapshot][Diag] Ergebnis leer. Gründe (Zähler): "
            f"muted/empty_tracks={empty_or_muted_tracks}, "
            f"no_marker_at_frame={no_marker_at_frame}, "
            f"muted_markers={muted_markers}"
        )
    else:
        preview = out[:5]
        print(
            f"[Snapshot][OK] aktive Marker={len(out)} (Preview {len(preview)}): "
            + ", ".join(f"{m['track']}@{m['frame']}" for m in preview)
        )

    return out

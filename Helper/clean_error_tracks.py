from __future__ import annotations

import bpy
import time
from bpy.types import Context


# ------------------------------------------------------------
# Helper: aktiven Clip finden
# ------------------------------------------------------------
def _find_active_clip(context: Context):
    """Find the active MovieClip, preferring Clip Editor, fallback Sequencer."""
    # Clip Editor bevorzugen
    wm = context.window_manager
    if wm is not None:
        for win in wm.windows:
            screen = win.screen
            if screen is None:
                continue
            for area in screen.areas:
                if area.type == 'CLIP_EDITOR':
                    space = area.spaces.active
                    if space and getattr(space, "clip", None):
                        return space.clip

    # Fallback: Sequencer-Strip mit Clip
    scene = context.scene
    if hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and getattr(strip, "clip", None):
            return strip.clip

    print("[CleanError] Kein aktiver Clip gefunden.")
    return None


# ------------------------------------------------------------
# Helper: Track-Error ermitteln
# ------------------------------------------------------------
def _get_track_error(track):
    """Retrieve average per-track error (solve or marker-based)."""
    # direkte Attribute versuchen
    for name in ("average_error", "error", "solve_error", "reprojection_error"):
        val = getattr(track, name, None)
        if val is not None:
            try:
                return float(val)
            except Exception:
                pass

    # Fallback: Marker-Errors mitteln (falls vorhanden)
    try:
        vals = [float(m.error) for m in track.markers if hasattr(m, "error")]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


# ------------------------------------------------------------
# Hauptfunktion: Clean Error Tracks
# ------------------------------------------------------------
def clean_error_tracks(context: Context, sort_desc: bool = True) -> int:
    scene = context.scene
    clip = _find_active_clip(context)
    if not clip:
        print("[CleanError] Kein aktiver Clip → ABORT")
        return 0

    tracks = getattr(clip.tracking, "tracks", [])
    if not tracks:
        print("[CleanError] Keine Tracks → ABORT")
        return 0

    results = []
    for t in tracks:
        err = _get_track_error(t)
        results.append({
            "name": t.name,
            "error": err,
            "track": t,
            "length": len(t.markers)
        })

    # Sortierung nach Error (None ans Ende)
    results.sort(
        key=lambda r: (r["error"] is None, -r["error"] if r["error"] else 0.0)
        if sort_desc else
        (r["error"] is None, r["error"] if r["error"] else 0.0)
    )

    valid = [r["error"] for r in results if r["error"] is not None]
    avg_error = sum(valid) / len(valid) if valid else None
    max_error_value = getattr(scene, "max_error_value", None)

    print("-------------------------------------------------")
    print(f"[CleanError] AVG_ERR={avg_error}, MAX_ERR={max_error_value}")
    print("-------------------------------------------------")

    if avg_error is None or max_error_value is None:
        print("[CleanError] Kein durchschnittlicher Fehler oder kein max_error_value → EXIT")
        return 0

    deleted = 0
    candidates_log = []
    deleted_log = []

    if avg_error > max_error_value:
        limit = avg_error * 2.0

        print(f"[CleanError] LIMIT für Löschung = {limit:.4f}")
        print("[CleanError] Kandidaten:")

        try:
            from ...Helper.delete import delete_track_by_name
        except Exception as e:
            print(f"[CleanError] delete_track_by_name Importfehler → EXIT ({e})")
            return 0

        # Kandidaten sammeln + loggen
        for r in results:
            if r["error"] is not None and r["error"] > limit:
                candidates_log.append(r)
                print(f" → DEL-Candidate: {r['name']} (Err={r['error']:.4f}, Len={r['length']})")

        print("[CleanError] Löschvorgang startet …")

        # Tatsächlich löschen + Log
        for r in candidates_log:
            try:
                delete_track_by_name(context, r["name"])
                deleted += 1
                deleted_log.append(r)
                print(f" ✔ GELÖSCHT: {r['name']} (Err={r['error']:.4f})")
            except Exception as e:
                print(f" ✖ FEHLGESCHLAGEN: {r['name']} ({e})")

    else:
        print("[CleanError] Kein Cleaning nötig (avg_error <= max_error_value).")
        return 0

    # Scene-Cache aktualisieren
    try:
        id_list = [str(id(t)) for t in clip.tracking.tracks]
        scene["best_track_ids"] = id_list
        scene["best_tracks"] = id_list
    except Exception as e:
        print(f"[CleanError] Fehler beim Aktualisieren von best_tracks: {e}")

    print("-------------------------------------------------")
    print(f"[CleanError] RESULT: Deleted={deleted}")
    print("[CleanError] Übrig gebliebene Tracks:",
          len(clip.tracking.tracks))
    print("-------------------------------------------------")

    time.sleep(0.5)
    return deleted

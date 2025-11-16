import bpy
import time

def clean_error_tracks(context: bpy.types.Context, sort_desc: bool = True) -> int:
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
        print("[CleanError] Kein durchschnittlicher Fehler vorhanden → EXIT")
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
        except Exception:
            print("[CleanError] delete_track_by_name Importfehler → EXIT")
            return 0

        for r in results:
            if r["error"] is not None and r["error"] > limit:
                candidates_log.append(r)
                print(f" → DEL-Candidate: {r['name']} (Err={r['error']:.4f}, Len={r['length']})")

        print("[CleanError] Löschvorgang startet …")

        for r in candidates_log:
            try:
                delete_track_by_name(context, r["name"])
                deleted += 1
                deleted_log.append(r)
                print(f" ✔ GELÖSCHT: {r['name']} (Err={r['error']:.4f})")
            except Exception:
                print(f" ✖ FEHLGESCHLAGEN: {r['name']}")

    else:
        print("[CleanError] Kein Cleaning nötig.")
        return 0

    # Refresh Scene Track-Cache
    id_list = [str(id(t)) for t in clip.tracking.tracks]
    scene["best_track_ids"] = id_list
    scene["best_tracks"] = id_list

    print("-------------------------------------------------")
    print(f"[CleanError] RESULT: Deleted={deleted}")
    print("[CleanError] Übrig gebliebene Tracks:",
          len(clip.tracking.tracks))
    print("-------------------------------------------------")

    time.sleep(0.5)
    return deleted

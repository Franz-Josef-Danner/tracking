import bpy

def _find_active_clip(context: bpy.types.Context):
    """Find the active MovieClip, preferring Clip Editor, fallback Sequencer."""
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'CLIP_EDITOR':
                space = area.spaces.active
                if space and getattr(space, "clip", None):
                    return space.clip
    scene = context.scene
    if hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and getattr(strip, "clip", None):
            return strip.clip
    return None


def _get_track_error(track):
    """Retrieve average per-track error (solve or marker-based)."""
    for name in ("average_error", "error", "solve_error", "reprojection_error"):
        val = getattr(track, name, None)
        if val is not None:
            try:
                return float(val)
            except Exception:
                pass
    try:
        vals = [float(m.error) for m in track.markers if hasattr(m, "error")]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


def clean_error_tracks(context: bpy.types.Context, sort_desc: bool = True) -> int:
    """
    Scans all tracks in the active clip, computes average error,
    deletes outliers if the mean error exceeds the scene threshold,
    and refreshes 'best_tracks' in the scene.
    
    Returns:
        int: Number of deleted tracks.
    """
    scene = context.scene
    clip = _find_active_clip(context)
    if not clip:
        return 0

    tracks = getattr(clip.tracking, "tracks", [])
    if not tracks:
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

    if avg_error is None or max_error_value is None:
        return 0

    deleted = 0
    if avg_error > max_error_value:
        limit = avg_error * 2.0
        try:
            from ...Helper.delete import delete_track_by_name
        except Exception:
            delete_track_by_name = None

        if delete_track_by_name:
            for r in results:
                if r["error"] is not None and r["error"] > limit:
                    try:
                        delete_track_by_name(context, r["name"])
                        deleted += 1
                    except Exception:
                        pass

    # Refresh stored track IDs
    try:
        for key in ("good_tracks", "best_tracks", "best_track_ids"):
            if key in scene:
                del scene[key]

        id_list = [str(id(t)) for t in clip.tracking.tracks]
        scene["best_track_ids"] = id_list
        scene["best_tracks"] = id_list
    except Exception:
        pass

    return deleted

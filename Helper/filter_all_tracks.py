# Helper/filter_all_tracks.py
def filter_and_delete_all_tracks(
    *,
    threshold: float = 30.0,
    clip: Optional[bpy.types.MovieClip] = None,
) -> Tuple[List[str], int]:
    tracking = _get_tracking(clip)
    if tracking is None or not getattr(tracking, "tracks", None):
        print("[FilterAll] ❌ Keine Tracks vorhanden.")
        return ([], 0)

    window, area, region, space = find_clip_editor_area(clip)
    if not window:
        print("[FilterAll] ❌ Kein CLIP_EDITOR-Kontext.")
        return ([], 0)

    override = {
        "window": window,
        "screen": window.screen,
        "area": area,
        "region": region,
        "space_data": space,
    }

    sel_snapshot = _snapshot_selection(tracking)

    try:
        _select_all(tracking)
        try:
            result = bpy.ops.clip.filter_tracks(override, track_threshold=float(threshold))
            if result != {'FINISHED'}:
                print("[FilterAll] ⚠️ Filter abgebrochen.")
                return ([], 0)
        except Exception:
            print("[FilterAll] ⚠️ Filterfehler.")
            return ([], 0)

        flagged_names = [t.name for t in tracking.tracks if t.select]
        if not flagged_names:
            print("[FilterAll] Keine fehlerhaften Tracks.")
            return ([], 0)

        deleted_count = delete_tracks_by_names(bpy.context, flagged_names)
        print(f"[FilterAll] 🗑️ {deleted_count} Tracks gelöscht.")
        return (flagged_names, int(deleted_count))

    finally:
        _restore_selection(tracking, sel_snapshot)

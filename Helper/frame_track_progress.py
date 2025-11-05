import bpy

# ------------------------------------------------------------
# Interner globaler Cache (Python-seitig, nicht in Scene)
# ------------------------------------------------------------
_progress_cache = {}

# ------------------------------------------------------------
# Fortschritts-Initialisierung und -Update
# ------------------------------------------------------------

def init_marker_progress(scene: bpy.types.Scene) -> None:
    """
    Initialisiert den Fortschrittscache für alle Frames auf 0 Marker.
    Legt eine leere Map im Python-Modulspeicher an und merkt sich
    die Scene-ID als Key.
    """
    key = str(id(scene))
    frame_start = scene.frame_start
    frame_end = scene.frame_end
    _progress_cache[key] = {f: 0 for f in range(frame_start, frame_end + 1)}

    # Reset UI-Wert
    if hasattr(scene, "kaiserlich_marker_progress"):
        scene.kaiserlich_marker_progress = "0%"

def update_marker_progress(scene: bpy.types.Scene, clip: bpy.types.MovieClip, current_frame: int, *, update_ui: bool = True) -> tuple[int, float]:
    """
    Aktualisiert den Fortschritt nur für den aktuellen Frame (O(1)).
    Arbeitet mit globalem Cache, der per Scene-ID adressiert wird.
    """
    key = str(id(scene))
    if key not in _progress_cache:
        init_marker_progress(scene)

    progress_map = _progress_cache[key]
    tracks = clip.tracking.tracks
    multi = getattr(scene, "kaiserlich_markers_per_frame", 1)
    if not tracks or multi <= 0:
        return 0, 0.0

    # Aktive Marker auf aktuellem Frame zählen
    count_this_frame = 0
    for tr in tracks:
        mk = tr.markers.find_frame(current_frame)
        if mk and not mk.mute:
            count_this_frame += 1
            if count_this_frame >= multi:
                break

    # Clampen und Map aktualisieren
    count_this_frame = min(count_this_frame, multi)
    progress_map[current_frame] = count_this_frame

    # Gesamtfortschritt berechnen
    frame_count = len(progress_map)
    total = sum(progress_map.values())
    goal = frame_count * multi
    perc = (100.0 * total / goal) if goal > 0 else 0.0

    # Fortschritt in Szene-Property schreiben
    if hasattr(scene, "kaiserlich_marker_progress"):
        scene.kaiserlich_marker_progress = f"{int(round(perc))}%"

    # UI Refresh throttlen (nicht bei jedem Frame nötig)
    if update_ui and (current_frame % 5 == 0):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()

    return count_this_frame, perc

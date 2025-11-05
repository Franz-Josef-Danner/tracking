# Helper/frame_track_progress.py
import bpy

# ------------------------------------------------------------
# Fortschritts-Initialisierung und -Update
# ------------------------------------------------------------

def init_marker_progress(scene: bpy.types.Scene) -> None:
    """
    Initialisiert die Fortschrittsmap für alle Frames auf 0 Marker.
    Wird beim Start eines Tracking-Zyklus aufgerufen.
    """
    frame_start = scene.frame_start
    frame_end   = scene.frame_end
    scene.kaiserlich_progress_map = {f: 0 for f in range(frame_start, frame_end + 1)}

    # Reset UI-Wert
    if hasattr(scene, "kaiserlich_marker_progress"):
        scene.kaiserlich_marker_progress = "0%"


def update_marker_progress(scene: bpy.types.Scene, clip: bpy.types.MovieClip, current_frame: int, *, update_ui: bool = True) -> tuple[int, float]:
    """
    Aktualisiert den Fortschritt nur für den aktuellen Frame.
    - Zählt aktive Marker (nicht gemutet)
    - Addiert in die Fortschrittsmap
    - Berechnet prozentualen Gesamtfortschritt
    Rückgabe: (marker_count_frame, total_percent)
    """
    tracks = clip.tracking.tracks
    multi  = getattr(scene, "kaiserlich_markers_per_frame", 1)
    if not tracks or multi <= 0:
        return 0, 0.0

    # Sicherstellen, dass ProgressMap existiert
    if not hasattr(scene, "kaiserlich_progress_map") or not scene.kaiserlich_progress_map:
        init_marker_progress(scene)

    progress_map = scene.kaiserlich_progress_map

    # Aktive Marker auf aktuellem Frame zählen
    count_this_frame = 0
    for tr in tracks:
        mk = tr.markers.find_frame(current_frame)
        if mk and not mk.mute:
            count_this_frame += 1
            if count_this_frame >= multi:
                break

    # Clampen und Map aktualisieren
    if count_this_frame > multi:
        count_this_frame = multi
    progress_map[current_frame] = count_this_frame

    # Gesamtfortschritt berechnen
    frame_count = len(progress_map)
    total = sum(progress_map.values())
    goal = frame_count * multi
    perc = (100.0 * total / goal) if goal > 0 else 0.0

    # UI-Update (String-Ausgabe)
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

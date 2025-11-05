import bpy

def compute_marker_progress(scene: bpy.types.Scene, *, update_ui: bool = True) -> tuple[int, float]:
    """
    Aggregiert pro Frame die Markeranzahl (gecappt auf `multi`) und berechnet den Fortschritt in %.
    Schreibt optional den Fortschritt in Szene-Properties (UI refresh optional).
    Rückgabe: (value, perc)
    """
    # Versuche zuerst Clip aus Clip Editor
    clip = None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                space = area.spaces.active
                if space and space.clip:
                    clip = space.clip
                    break
        if clip:
            break

    # Fallback auf Sequencer (nicht ideal, aber failsafe)
    if clip is None and hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and hasattr(strip, "clip"):
            clip = strip.clip

    if clip is None:
        raise RuntimeError("[Kaiserlich Tracker] Kein aktiver Movie Clip gefunden.")

    tracks = clip.tracking.tracks
    if not tracks:
        return 0, 0.0

    frame_start = scene.frame_start
    frame_end   = scene.frame_end
    multi       = getattr(scene, "kaiserlich_markers_per_frame", 1)

    if frame_end <= frame_start or multi <= 0:
        return 0, 0.0

    scene_duration = frame_end - frame_start + 1
    goal = scene_duration * multi
    value = 0

    # Frameweise Marker zählen
    for f in range(frame_start, frame_end + 1):
        count_this_frame = 0
        for tr in tracks:
            for m in tr.markers:
                if m.frame == f:
                    count_this_frame += 1
                    if count_this_frame >= multi:
                        break
            if count_this_frame >= multi:
                break

        # Cap auf multi
        if count_this_frame > multi:
            count_this_frame = multi
        value += count_this_frame

    perc = (100.0 * value / goal) if goal > 0 else 0.0

    # Optional in Szene schreiben
    if hasattr(scene, "kaiserlich_marker_progress"):
        scene.kaiserlich_marker_progress = perc

    # Optional UI refreshen
    if update_ui:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()

    return value, perc

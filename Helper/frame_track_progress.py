import bpy

def compute_marker_progress(scene: bpy.types.Scene) -> tuple[int, float]:
    """
    Aggregiert pro Frame die Markeranzahl (gecappt auf `multi`) und berechnet den Fortschritt in %.
    Rückgabe: (value, perc)
    """
    clip = scene.sequence_editor_active_strip.clip if hasattr(scene, "sequence_editor_active_strip") else None
    # Besser direkt aus dem Clip-Editor:
    space = next((a.spaces.active for w in bpy.context.window_manager.windows
                  for a in w.screen.areas if a.type == 'CLIP_EDITOR'), None)
    if space and space.clip:
        clip = space.clip
    if clip is None:
        raise RuntimeError("Kein aktiver Movie Clip im CLIP_EDITOR gefunden.")

    tracks = clip.tracking.tracks
    if not tracks:
        return 0, 0.0

    frame_start = scene.frame_start
    frame_end   = scene.frame_end
    multi       = getattr(scene, "kaiserlich_markers_per_frame", 1)

    # Schutzklauseln
    if frame_end <= frame_start:
        return 0, 0.0
    if multi <= 0:
        return 0, 0.0

    scene_duration = frame_end - frame_start + 1
    goal = scene_duration * multi

    value = 0

    # Pro Frame Marker zählen (nur vorhandene Marker auf exakt diesem Frame)
    for f in range(frame_start, frame_end + 1):
        count_this_frame = 0
        for tr in tracks:
            # Direktzugriff auf Marker-Liste:
            # Wir iterieren nur bis wir > multi sind (Frühausstieg für Performance)
            for m in tr.markers:
                if m.frame == f:
                    count_this_frame += 1
                    if count_this_frame >= multi:
                        # capping erreicht, weiteren Aufwand sparen
                        break
            if count_this_frame >= multi:
                break

        # Cap auf multi
        if count_this_frame > multi:
            count_this_frame = multi

        value += count_this_frame

    perc = (100.0 * value / goal) if goal > 0 else 0.0
    return value, perc


# Beispielnutzung + optionale UI-Sync
try:
    val, perc = compute_marker_progress(bpy.context.scene)
    # Szene-Properties aktualisieren (falls vorhanden)
    s = bpy.context.scene
    if hasattr(s, "kaiserlich_progress_title"):
        s.kaiserlich_progress_title = f"Single Tests: {int(round(perc))}%"
    if hasattr(s, "kaiserlich_progress_step"):
        s.kaiserlich_progress_step = f"Total: {int(round(perc))}%"

    # UI-Region refreshen (gezielt CLIP_EDITOR/ UI)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()
except Exception as e:
    print(f"[MarkerProgress] Fehler: {e}")

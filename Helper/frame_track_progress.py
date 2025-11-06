# Helper/frame_track_progress.py
import bpy

def compute_marker_progress(scene: bpy.types.Scene, *, update_ui: bool = True) -> tuple[int, float]:
    """
    Aggregiert pro Frame die Markeranzahl (gecappt auf `multi`) und berechnet den Fortschritt in %.
    Schreibt optional den Fortschritt in Szene-Properties (UI refresh optional).
    Rückgabe: (value, perc)
    """
    # --- Clip ermitteln (unverändert zur bisherigen Kommunikation) ---
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

    # Fallback (unverändert)
    if clip is None and hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and hasattr(strip, "clip"):
            clip = strip.clip

    if clip is None:
        raise RuntimeError("[Kaiserlich Tracker] Kein aktiver Movie Clip gefunden.")

    # --- Sicherstellen, dass überhaupt Tracks existieren ---
    tracks = getattr(clip.tracking, "tracks", [])
    if not tracks or len(tracks) == 0:
        # Keine Tracks vorhanden → Fortschritt 0%
        if hasattr(scene, "kaiserlich_marker_progress"):
            scene.kaiserlich_marker_progress = "0%"
        if update_ui:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "CLIP_EDITOR":
                        for region in area.regions:
                            if region.type == "UI":
                                region.tag_redraw()
        return (0, 0.0)

    # --- Eingangsparameter & Zielgröße ---
    frame_start = int(scene.frame_start)
    frame_end   = int(scene.frame_end)
    multi       = int(getattr(scene, "kaiserlich_markers_per_frame", 1))

    if frame_end < frame_start or multi <= 0:
        return 0, 0.0

    # inkl. Endframe rechnen
    scene_duration = (frame_end - frame_start + 1)
    goal = scene_duration * multi
    if goal <= 0:
        return 0, 0.0

    # --- Pro-Frame-Zählung (robust & effizient) ---
    # Sammeln der Marker-Anzahlen je Frame in einem Durchlauf über alle Marker
    per_frame_counts = {f: 0 for f in range(frame_start, frame_end + 1)}
    for tr in tracks:
        # Falls nur „aktive/gültige“ Marker zählen sollen, hier optional filtern (mk.mute, tr.mute, etc.)
        for mk in tr.markers:
            f = mk.frame
            if frame_start <= f <= frame_end and not mk.mute:
                # Frühzeitige Kappung auf multi spart Summationszeit bei sehr dichter Markerdichte
                if per_frame_counts[f] < multi:
                    per_frame_counts[f] += 1

    # --- Aggregation mit Cap pro Frame ---
    value = 0
    for f in range(frame_start, frame_end + 1):
        # per_frame_counts[f] ist bereits auf multi gekappt
        value += per_frame_counts[f]
    # Prozentwert strikt nach unten runden; 100 % nur bei value >= goal
    if goal > 0:
        perc_raw = 100.0 * value / goal
        perc = float(int(perc_raw))  # floor via int()
        if value < goal and perc >= 100.0:
            perc = 99.0
    else:
        perc = 0.0

    # --- UI/Properties (Kommunikation unverändert) ---
    if hasattr(scene, "kaiserlich_marker_progress"):
        # UI zeigt denselben strikt abgerundeten Wert
        scene.kaiserlich_marker_progress = f"{int(perc)}%"

    if update_ui:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'CLIP_EDITOR':
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()

    return value, perc

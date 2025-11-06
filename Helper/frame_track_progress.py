# Helper/frame_track_progress.py
import bpy
from .track_quality_metrics import compute_track_quality_metrics  # 🔹 Qualität einbinden

def compute_marker_progress(scene: bpy.types.Scene, *, update_ui: bool = True) -> tuple[int, float]:
    """
    Aggregiert pro Frame die Markeranzahl (gecappt auf `multi`) und berechnet den Fortschritt in %.
    Ergänzt um Qualitätseinfluss: effektiver Fortschritt = Fortschritt * (Qualität / 100).
    Rückgabe: (value, perc_effektiv)
    """
    # --- Clip ermitteln (unverändert) ---
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

    if clip is None and hasattr(scene, "sequence_editor_active_strip"):
        strip = scene.sequence_editor_active_strip
        if strip and hasattr(strip, "clip"):
            clip = strip.clip

    if clip is None:
        raise RuntimeError("[Kaiserlich Tracker] Kein aktiver Movie Clip gefunden.")

    # --- Sicherstellen, dass überhaupt Tracks existieren ---
    tracks = getattr(clip.tracking, "tracks", [])
    if not tracks:
        if hasattr(scene, "kaiserlich_marker_progress"):
            scene.kaiserlich_marker_progress = "0%"
        if update_ui:
            _refresh_ui()
        return (0, 0.0)

    frame_start = int(scene.frame_start)
    frame_end   = int(scene.frame_end)
    multi       = int(getattr(scene, "kaiserlich_markers_per_frame", 1))

    if frame_end < frame_start or multi <= 0:
        return 0, 0.0

    scene_duration = (frame_end - frame_start + 1)
    goal = scene_duration * multi
    if goal <= 0:
        return 0, 0.0

    # --- Marker zählen ---
    per_frame_counts = {f: 0 for f in range(frame_start, frame_end + 1)}
    for tr in tracks:
        for mk in tr.markers:
            f = mk.frame
            if frame_start <= f <= frame_end and not mk.mute:
                if per_frame_counts[f] < multi:
                    per_frame_counts[f] += 1

    value = sum(per_frame_counts.values())

    if goal > 0:
        perc_raw = 100.0 * value / goal
        perc = float(int(perc_raw))  # floor
        if value < goal and perc >= 100.0:
            perc = 99.0
    else:
        perc = 0.0

    # --- Qualität abrufen und kombinieren ---
    try:
        quality_data = compute_track_quality_metrics(bpy.context)
        qual = quality_data.get("prozent", 100.0)
    except Exception as e:
        print(f"[Kaiserlich Tracker][Quality] ⚠️ Qualitätsberechnung fehlgeschlagen: {e}")
        qual = 100.0

    perc_effektiv = round(perc * (qual / 100.0), 1)

    # --- UI/Properties ---
    if hasattr(scene, "kaiserlich_marker_progress"):
        scene.kaiserlich_marker_progress = f"{int(perc_effektiv)}%"

    if update_ui:
        _refresh_ui()

    print(f"[Kaiserlich Tracker] Fortschritt: {perc:.1f}%, Qualität: {qual:.1f}%, Effektiv: {perc_effektiv:.1f}%")

    return value, perc_effektiv


def _refresh_ui():
    """Hilfsfunktion für UI-Redraw (sauber ausgelagert)."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()

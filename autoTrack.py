import bpy
import ctypes

# Windows-Konsole anzeigen (nur Windows)
ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)

# Thresholds von stabil bis sensibel
THRESHOLDS = [1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.005, 0.001]


def get_clip_context():
    for area in bpy.context.window.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    space = next(s for s in area.spaces if s.type == 'CLIP_EDITOR' and s.clip)
                    return {
                        "area": area,
                        "region": region,
                        "space_data": space,
                        "scene": bpy.context.scene,
                        "window": bpy.context.window,
                        "screen": bpy.context.screen,
                    }
    raise RuntimeError("Kein aktiver Clip im Motion Tracking Editor gefunden.")


def count_active_tracks(frame, tracks):
    """Anzahl der Marker, die auf dem gegebenen Frame existieren."""
    return sum(1 for t in tracks if any(m.frame == frame for m in t.markers))


def dynamic_track(min_active=20, continue_until=15):
    """Suche Marker, bis min_active Marker vorhanden sind.
    Danach Tracken, bis nur noch continue_until Marker aktiv sind.
    Anschließend erneut Marker suchen usw.
    """
    ctx = get_clip_context()
    clip = ctx["space_data"].clip
    tracks = clip.tracking.tracks

    start = int(clip.frame_start)
    end = start + int(clip.frame_duration) - 1
    frame = start

    print(f"Starte automatisches Tracking von {start} bis {end}")

    while frame <= end:
        bpy.context.scene.frame_current = frame

        # Marker suchen bis Mindestanzahl erreicht ist
        while count_active_tracks(frame, tracks) < min_active:
            for th in THRESHOLDS:
                with bpy.context.temp_override(**ctx):
                    bpy.ops.clip.detect_features(threshold=th)
                if count_active_tracks(frame, tracks) >= min_active:
                    break
            else:
                # Nicht genug Marker, obwohl alle Thresholds ausprobiert wurden
                break

        # Marker solange tracken, bis nur noch continue_until übrig sind
        while frame < end and count_active_tracks(frame, tracks) > continue_until:
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            frame += 1
            bpy.context.scene.frame_current = frame

        # nach Tracking beginnt die Suche erneut (while frame loop setzt sie fort)
        frame += 0  # Schleifenvariable für Klarheit beibehalten

    print("Automatisches Tracking beendet.")


if __name__ == "__main__":
    dynamic_track()

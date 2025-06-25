import bpy
import ctypes

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20


def get_clip_context():
    """Return a context with an active clip-editor and clip."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            for space in area.spaces:
                if space.type == 'CLIP_EDITOR' and space.clip:
                    region = next(r for r in area.regions if r.type == 'WINDOW')
                    return {
                        "window": window,
                        "screen": screen,
                        "area": area,
                        "region": region,
                        "space_data": space,
                        "scene": bpy.context.scene,
                    }
    raise RuntimeError("Kein aktiver Clip im Motion Tracking Editor gefunden.")


def detect_features_until_enough():
    ctx = get_clip_context()
    tracks = ctx["space_data"].clip.tracking.tracks
    threshold = 1.0
    while True:
        before = len(tracks)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.detect_features(threshold=threshold, margin=5, distance=200)
        new_markers = len(tracks) - before
        print(f"Threshold {threshold:.3f}: {new_markers} neue Marker")
        if len(tracks) >= MIN_MARKERS:
            print(f"✅ {len(tracks)} Marker erreicht")
            break
        print(f"⚠ Nur {len(tracks)} Marker – entferne Marker")
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.select_all(action='SELECT')
            bpy.ops.clip.delete_track()
        threshold -= 0.001
        if threshold <= 0:
            print("❌ Kein passender Threshold gefunden")
            break


if __name__ == "__main__":
    detect_features_until_enough()

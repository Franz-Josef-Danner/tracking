import bpy
import ctypes

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20
THRESHOLDS = [1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.005, 0.001, 0.0005, 0.0001]


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
    for th in THRESHOLDS:
        before = len(tracks)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.detect_features(threshold=th)
        new_markers = len(tracks) - before
        print(f"Threshold {th:.4f}: {new_markers} neue Marker")
        if len(tracks) >= MIN_MARKERS:
            print(f"✅ {len(tracks)} Marker erreicht")
            break
    else:
        print(f"⚠ Nur {len(tracks)} Marker nach allen Thresholds")


if __name__ == "__main__":
    detect_features_until_enough()

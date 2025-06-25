import bpy
import ctypes

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20


def count_active_markers(tracks, frame):
    """Return the number of markers that exist for the given frame."""
    count = 0
    for track in tracks:
        for marker in track.markers:
            if marker.frame == frame and not getattr(marker, "mute", False):
                count += 1
                break
    return count


def track_until_too_few(ctx, clip):
    """Track step by step and stop if marker count drops too low."""
    tracks = clip.tracking.tracks
    scene = ctx["scene"]
    frame_end = scene.frame_end
    stop_count = int(MIN_MARKERS * 0.9)
    current = scene.frame_current
    while current < frame_end:
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.track_markers(backwards=False, sequence=False)
        current += 1
        scene.frame_current = current
        active = count_active_markers(tracks, current)
        print(f"Frame {current}: {active} Marker", flush=True)
        if active < stop_count:
            print(
                f"⛔ Tracking gestoppt – nur noch {active} Marker (Minimum {stop_count})",
                flush=True,
            )
            break


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
    clip = ctx["space_data"].clip
    tracks = clip.tracking.tracks
    width = clip.size[0]
    # margin and min_distance scale with clip width
    margin = int(width / 200)
    distance = int(width / 20)
    threshold = 1.0
    print(
        f"Starte Feature Detection: width={width}, margin={margin}, min_distance={distance}, min_markers={MIN_MARKERS}",
        flush=True,
    )
    while True:
        before = len(tracks)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
            )
        after = len(tracks)
        added = after - before
        print(
            f"Threshold {threshold:.3f}: {added} neue Marker (insgesamt {after})",
            flush=True,
        )
        if after >= MIN_MARKERS:
            print(f"✅ {after} Marker erreicht", flush=True)
            print("Starte Tracking ...", flush=True)
            track_until_too_few(ctx, clip)
            break
        print(f"⚠ Nur {after} Marker – entferne Marker", flush=True)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.select_all(action='SELECT')
            bpy.ops.clip.delete_track()
        if added > 0:
            threshold /= (MIN_MARKERS / added)
        else:
            threshold -= 0.1
        if threshold < 0.0001:
            threshold = 0.0001
        if threshold == 0.0001 and after < MIN_MARKERS:
            print("❌ Kein passender Threshold gefunden", flush=True)
            break
        print(f"→ Neuer Threshold: {threshold:.4f}", flush=True)


if __name__ == "__main__":
    detect_features_until_enough()

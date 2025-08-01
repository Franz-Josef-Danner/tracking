import bpy
import time

def wait_for_marker_change(context, timeout=1.0):
    """Warte, bis sich die Anzahl der Marker ändert oder Timeout erreicht ist."""
    clip = context.edit_movieclip or context.scene.clip
    if not clip:
        print("[Fehler] Kein Clip aktiv.")
        return False

    def marker_count():
        return sum(len(track.markers) for track in clip.tracking.tracks)

    initial_count = marker_count()
    start_time = time.time()
    while time.time() - start_time < timeout:
        if marker_count() != initial_count:
            return True
        time.sleep(0.1)
    return False

def evaluate_tracking(context):
    print("[Info] Starte mit vorhandenen Marker – keine Löschung, nur neue setzen.")
    bpy.ops.tracking.place_marker()
    wait_for_marker_change(context)
    bpy.ops.tracking.track_markers('INVOKE_DEFAULT', forwards=True)
    time.sleep(0.1)  # kurze Pause nach Tracking
    return calculate_score(context)

def calculate_score(context):
    clip = context.edit_movieclip or context.scene.clip
    if not clip:
        return float('inf')
    scores = []
    for track in clip.tracking.tracks:
        errors = [p.error for p in track.markers if hasattr(p, 'error')]
        if errors:
            scores.append(sum(errors) / len(errors))
    return sum(scores) / len(scores) if scores else float('inf')

def run_tracking_optimization(context):
    settings = context.scene.tracking_settings

    best_pattern = None
    best_pattern_score = float('inf')
    for pattern_size in [5, 9, 13, 17]:
        settings.default_pattern_size = pattern_size
        settings.default_search_size = pattern_size * 2
        score = evaluate_tracking(context)
        print(f"[Score] Pattern {pattern_size}: {score:.4f}")
        if score < best_pattern_score:
            best_pattern_score = score
            best_pattern = pattern_size
    settings.default_pattern_size = best_pattern
    settings.default_search_size = best_pattern * 2
    print(f"[Besteinstellung] Pattern: {best_pattern}")

    best_motion = None
    best_motion_score = float('inf')
    for model in ['Loc', 'LocRot', 'Affine']:  # Beispielwerte
        settings.default_motion_model = model
        score = evaluate_tracking(context)
        print(f"[Score] Motion {model}: {score:.4f}")
        if score < best_motion_score:
            best_motion_score = score
            best_motion = model
    settings.default_motion_model = best_motion
    print(f"[Besteinstellung] Motion: {best_motion}")

    best_channels = None
    best_channel_score = float('inf')
    for red in [True, False]:
        for green in [True, False]:
            if not red and not green:
                continue
            settings.use_default_red_channel = red
            settings.use_default_green_channel = green
            score = evaluate_tracking(context)
            print(f"[Score] Channels R:{red} G:{green}: {score:.4f}")
            if score < best_channel_score:
                best_channel_score = score
                best_channels = (red, green)
    if best_channels:
        settings.use_default_red_channel, settings.use_default_green_channel = best_channels
        print(f"[Besteinstellung] Channels: R:{best_channels[0]} G:{best_channels[1]}")

    return {
        "pattern": best_pattern,
        "motion": best_motion,
        "channels": best_channels
    }

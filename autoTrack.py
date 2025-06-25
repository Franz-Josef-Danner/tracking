import bpy
import ctypes
from math import log10

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20
MIN_TRACK_LENGTH = 10
# Prefixes used to separate newly added and permanent tracks
NEW_PREFIX = "NEW_"
LOCKED_PREFIX = "LOCKED_"
# Motion models to cycle through when tracking stalls
MOTION_MODELS = [
    "Perspective",
    "Affine",
    "LocRotScale",
    "LocRot",
    "Loc",
]


def escape_pressed() -> bool:
    """Return True if the Escape key is currently pressed."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    except Exception:
        return False



class WM_OT_auto_track(bpy.types.Operator):
    """Operator um Tracking mit Eingabeparameter zu starten"""

    bl_idname = "wm.auto_track"
    bl_label = "Auto Track"

    min_markers: bpy.props.IntProperty(
        name="Mindestanzahl Marker",
        default=20,
        min=1,
    )
    min_track_length: bpy.props.IntProperty(
        name="Mindestanzahl Frames",
        default=10,
        min=1,
    )

    def invoke(self, context, event):
        self.min_markers = MIN_MARKERS
        self.min_track_length = MIN_TRACK_LENGTH
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        global MIN_MARKERS, MIN_TRACK_LENGTH
        MIN_MARKERS = self.min_markers
        MIN_TRACK_LENGTH = self.min_track_length
        initial_min_markers = MIN_MARKERS
        print(
            f"Nutze MIN_MARKERS={MIN_MARKERS}, MIN_TRACK_LENGTH={MIN_TRACK_LENGTH}",
            flush=True,
        )
        if not detect_features_until_enough(
            initial_min_markers,
            max_attempts=10,
        ):
            print("🏁 Beende Auto-Tracking", flush=True)
            return {'CANCELLED'}

        result = {'FINISHED'}
        ctx = get_clip_context()
        clip = ctx["space_data"].clip
        frame_end = clip.frame_start + clip.frame_duration - 1
        model_index = 0
        attempts = 0

        while bpy.context.scene.frame_current < frame_end:
            motion_model = MOTION_MODELS[model_index]
            if not track_existing_markers(motion_model):
                model_index = (model_index + 1) % len(MOTION_MODELS)
                attempts += 1
                if attempts >= len(MOTION_MODELS):
                    print("❌ Tracking stagniert mit allen Motion Models", flush=True)
                    result = {'CANCELLED'}
                    break
                print(
                    f"🔄 Selber Frame erneut erreicht – wechsle Motion Model zu {MOTION_MODELS[model_index]}",
                    flush=True,
                )
            else:
                attempts = 0

        print("🏁 Beende Auto-Tracking", flush=True)
        return result


def track_span(track):
    """Return the first and last tracked frame of a track."""
    frames = [m.frame for m in track.markers if not m.mute]
    if not frames:
        return None, None
    return min(frames), max(frames)


def track_length(track):
    """Return the tracked frame span of a track."""
    start, end = track_span(track)
    if start is None:
        return 0
    return end - start + 1


def rename_new_tracks(tracks, before_names):
    """Prefix newly created tracks so they can be distinguished."""
    for track in tracks:
        if track.name not in before_names and not track.name.startswith(NEW_PREFIX):
            track.name = f"{NEW_PREFIX}{track.name}"


def delete_short_tracks(ctx, clip):
    """Remove short tracks and lock long living ones."""
    tracks = clip.tracking.tracks
    removed = 0
    with bpy.context.temp_override(**ctx):
        for track in list(tracks):
            length = track_length(track)
            is_locked = track.lock or track.name.startswith(LOCKED_PREFIX)
            if length >= MIN_TRACK_LENGTH and not is_locked:
                track.name = f"{LOCKED_PREFIX}{track.name}"
                track.lock = True
            if length < MIN_TRACK_LENGTH and not is_locked:
                track.select = True
            else:
                track.select = False

        if any(track.select for track in tracks):
            bpy.ops.clip.delete_track()
            removed = sum(1 for track in tracks if track.select)
            if removed:
                print(
                    f"🗑 Entferne {removed} kurze Tracks (<{MIN_TRACK_LENGTH} Frames)",
                    flush=True,
                )


def print_track_lengths(clip):
    """Gibt die Länge aller Tracks aus."""
    print("📊 Track-Längen:", flush=True)
    for track in clip.tracking.tracks:
        length = track_length(track)
        start, end = track_span(track)
        if start is None:
            continue
        print(
            f"    {track.name}: {length} Frames (von {start} bis {end})",
            flush=True,
        )


def find_first_frame_with_min_tracks(clip, min_markers):
    """Return the first frame with only ``min_markers`` active tracks."""
    start_frame = clip.frame_start
    end_frame = start_frame + clip.frame_duration - 1
    tracks = clip.tracking.tracks
    for frame in range(start_frame, end_frame + 1):
        active = 0
        for track in tracks:
            if any(m.frame == frame and not m.mute for m in track.markers):
                active += 1
        if active <= min_markers:
            return frame
    return None


def move_playhead_to_min_tracks(ctx, clip, min_markers):
    """Set the playhead to the frame where only ``min_markers`` remain."""
    frame = find_first_frame_with_min_tracks(clip, min_markers)
    if frame is None:
        return
    with bpy.context.temp_override(**ctx):
        bpy.context.scene.frame_set(frame)
    print(
        f"⏩ Setze Playhead auf Frame {frame} (nur noch {min_markers} aktive Tracks)",
        flush=True,
    )


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


def detect_features_until_enough(
    playhead_min_markers=None,
    *,
    max_attempts=5,
    min_threshold=0.0001,
):
    ctx = get_clip_context()
    clip = ctx["space_data"].clip
    tracks = clip.tracking.tracks
    width = clip.size[0]
    # margin and min_distance scale with clip width
    margin = int(width / 200)
    threshold = 0.1
    distance = int(int(width / 40) / (((log10(threshold) / -1) + 1) / 2))
    target_markers = MIN_MARKERS * 4
    print(
        f"Starte Feature Detection: width={width}, margin={margin}, min_distance={distance}, "
        f"min_markers={MIN_MARKERS}, min_track_length={MIN_TRACK_LENGTH}",
        flush=True,
    )
    print("Drücke ESC, um abzubrechen", flush=True)
    success = False
    attempts = 0
    while True:
        attempts += 1
        if escape_pressed():
            print("❌ Abgebrochen mit Escape", flush=True)
            break
        distance = int(int(width / 40) / (((log10(threshold) / -1) + 1) / 2))
        before_names = {t.name for t in tracks}
        # Setze Playhead auf aktuellen Frame, damit neue Marker dort starten
        current_frame = bpy.context.scene.frame_current
        with bpy.context.temp_override(**ctx):
            bpy.context.scene.frame_set(current_frame)
            ctx["space_data"].clip_user.frame_current = current_frame
            bpy.ops.clip.detect_features(
                threshold=threshold,
                margin=margin,
                min_distance=distance,
            )
        rename_new_tracks(tracks, before_names)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.select_all(action='SELECT')
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        delete_short_tracks(ctx, clip)
        after = len(tracks)
        added = after - len(before_names)
        print(
            f"Threshold {threshold:.3f}: {added} neue Marker (insgesamt {after})",
            flush=True,
        )
        if after >= target_markers:
            print(f"✅ {after} Marker erreicht", flush=True)
            print_track_lengths(clip)
            move_playhead_to_min_tracks(
                ctx,
                clip,
                MIN_MARKERS if playhead_min_markers is None else playhead_min_markers,
            )
            success = True
            break
        print(f"⚠ Nur {after} Marker – versuche erneut", flush=True)
        if added > 0:
            threshold /= (target_markers / added)
        else:
            threshold -= 0.1
        if threshold < min_threshold:
            threshold = min_threshold
        if threshold == min_threshold and after < target_markers:
            print("❌ Kein passender Threshold gefunden", flush=True)
            break
        if max_attempts is not None and attempts >= max_attempts:
            print(
                f"❌ Maximalzahl an Versuchen ({max_attempts}) erreicht",
                flush=True,
            )
            break
        print(f"→ Neuer Threshold: {threshold:.4f}", flush=True)
    return success


def track_existing_markers(motion_model="Perspective"):
    """Track existing markers once using the given motion model."""
    ctx = get_clip_context()
    clip = ctx["space_data"].clip
    clip.tracking.settings.default_motion_model = motion_model
    print(f"📐 Nutze Motion Model {motion_model}", flush=True)
    prev_frame = bpy.context.scene.frame_current
    with bpy.context.temp_override(**ctx):
        bpy.ops.clip.select_all(action='SELECT')
        bpy.ops.clip.track_markers(backwards=False, sequence=True)
    current_frame = bpy.context.scene.frame_current
    return current_frame != prev_frame

def register():
    bpy.utils.register_class(WM_OT_auto_track)


def unregister():
    bpy.utils.unregister_class(WM_OT_auto_track)


if __name__ == "__main__":
    register()
    bpy.ops.wm.auto_track('INVOKE_DEFAULT')





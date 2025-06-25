import bpy
import ctypes

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20
MIN_TRACK_LENGTH = 10



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
        print(
            f"Nutze MIN_MARKERS={MIN_MARKERS}, MIN_TRACK_LENGTH={MIN_TRACK_LENGTH}",
            flush=True,
        )
        detect_features_until_enough()
        return {'FINISHED'}


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


def delete_short_tracks(ctx, clip):
    """Remove tracks shorter than the minimum length."""
    tracks = clip.tracking.tracks
    removed = 0
    with bpy.context.temp_override(**ctx):
for track in list(tracks):
    if track_length(track) < MIN_TRACK_LENGTH:
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
        f"Starte Feature Detection: width={width}, margin={margin}, min_distance={distance}, "
        f"min_markers={MIN_MARKERS}, min_track_length={MIN_TRACK_LENGTH}",
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
            start_frame = clip.frame_start
            end_frame = start_frame + clip.frame_duration - 1
            print(
                f"Starte Tracking von Frame {start_frame} bis {end_frame} ...",
                flush=True,
            )
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.track_markers(backwards=False, sequence=True)
            delete_short_tracks(ctx, clip)
            print_track_lengths(clip)
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


def register():
    bpy.utils.register_class(WM_OT_auto_track)


def unregister():
    bpy.utils.unregister_class(WM_OT_auto_track)


if __name__ == "__main__":
    register()
    bpy.ops.wm.auto_track('INVOKE_DEFAULT')



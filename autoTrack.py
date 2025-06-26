import bpy
import ctypes
from math import log10
import time

# Show console on Windows
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)
except Exception:
    pass

MIN_MARKERS = 20
MIN_TRACK_LENGTH = 10
# Factor to temporarily raise the detection target
MARKER_MULTIPLIER = 4
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
MAX_CYCLES = 100
TARGET_DELTA = 10  # Additional markers to reach when detecting features



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
        original_model_index = 0
        print(
            f"Nutze MIN_MARKERS={MIN_MARKERS}, MIN_TRACK_LENGTH={MIN_TRACK_LENGTH}",
            flush=True,
        )
        result = {'FINISHED'}
        autotracker = AutoTracker()
        ctx = autotracker.ctx
        clip = autotracker.clip
        prev_frame = bpy.context.scene.frame_current
        model_index = original_model_index
        marker_boost = 0
        max_cycles = MAX_CYCLES
        cycle_count = 0
        start_time_all = time.time()
        while True:
            cycle_start = time.time()
            cycle_count += 1
            if cycle_count >= max_cycles:
                print(
                    f"❌ Maximalanzahl an Trackingzyklen ({max_cycles}) erreicht – Abbruch",
                    flush=True,
                )
                result = {'CANCELLED'}
                break
            motion_model = MOTION_MODELS[model_index]
            print(
                f"📊 Tracking Zyklus {cycle_count}: Modell = {motion_model}, MIN_MARKERS = {MIN_MARKERS}",
                flush=True,
            )
            if "last_threshold" in clip:
                print(f"📉 Letzter Threshold: {clip['last_threshold']:.4f}", flush=True)
            if not detect_features_until_enough(
                motion_model,
                initial_min_markers,
                max_attempts=50,
            ):
                result = {'CANCELLED'}
                break

            delete_short_tracks(ctx, clip)
            move_playhead_to_min_tracks(ctx, clip, initial_min_markers)
            bpy.context.view_layer.update()

            current_frame = bpy.context.scene.frame_current
            if current_frame == prev_frame:
                marker_boost += 10
                MIN_MARKERS = initial_min_markers + marker_boost
                model_index = (model_index + 1) % len(MOTION_MODELS)
                print(
                    f"🔄 Selber Frame erneut erreicht – erhöhe MIN_MARKERS auf {MIN_MARKERS} "
                    f"und wechsle Motion Model zu {MOTION_MODELS[model_index]}",
                    flush=True,
                )
            else:
                if model_index != original_model_index:
                    print(
                        f"✅ Fortschritt erkannt – setze Motion Model zurück auf {MOTION_MODELS[original_model_index]}",
                        flush=True,
                    )
                model_index = original_model_index
                if marker_boost > 0:
                    marker_boost -= 10
                    MIN_MARKERS = initial_min_markers + marker_boost
                    print(f"⬇ MIN_MARKERS reduziert auf {MIN_MARKERS}", flush=True)
            cycle_duration = time.time() - cycle_start
            print(f"⏱ Zyklusdauer: {cycle_duration:.2f} Sekunden", flush=True)
            prev_frame = current_frame

            if find_first_frame_with_min_tracks(clip, initial_min_markers) is None:
                print("✅ Keine schwachen Stellen mehr gefunden", flush=True)
                break
        print("🏁 Beende Auto-Tracking", flush=True)
        total_duration = time.time() - start_time_all
        print(f"⏱ Gesamtdauer: {total_duration:.2f} Sekunden", flush=True)
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


def delete_new_tracks(tracks):
    """Löscht alle Tracks, die mit NEW_ beginnen."""
    for track in list(tracks):
        if track.name.startswith(NEW_PREFIX):
            tracks.remove(track)
            print(f"🗑 Entferne neuen Marker: {track.name}", flush=True)


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


class AutoTracker:
    """Helper to encapsulate context and clip for tracking."""

    def __init__(self, context=None):
        self.ctx = context if context is not None else get_clip_context()
        self.clip = self.ctx["space_data"].clip


def detect_features_until_enough(
    motion_model="Perspective",
    playhead_min_markers=None,
    *,
    max_attempts=5,
    min_threshold=0.0001,
):
    autotracker = AutoTracker()
    ctx = autotracker.ctx
    clip = autotracker.clip
    clip.tracking.settings.default_motion_model = motion_model
    print(
        f"📐 Nutze Motion Model {clip.tracking.settings.default_motion_model}",
        flush=True,
    )
    tracks = clip.tracking.tracks
    width = clip.size[0]
    # margin and min_distance scale with clip width
    margin = int(width / 200)
    threshold = 0.1
    last_threshold = threshold  # Für externe Anzeige
    distance = int(int(width / 40) / (((log10(threshold) / -1) + 1) / 2))
    existing_tracks = len(tracks)
    target_markers = MIN_MARKERS * MARKER_MULTIPLIER
    print(
        f"Starte Feature Detection: width={width}, margin={margin}, min_distance={distance}, "
        f"min_markers={MIN_MARKERS}, target_markers={target_markers}, min_track_length={MIN_TRACK_LENGTH}",
        flush=True,
    )
    lower_bound = int(target_markers * 0.8)
    upper_bound = int(target_markers * 1.2)
    print(
        f"🎯 Ziel: {target_markers} Marker ±20% → erlaubt: {lower_bound} bis {upper_bound}",
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
            # Tracking vorher ausführen
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        # Dann auswerten, ob die neuen Tracks lang genug waren
        delete_short_tracks(ctx, clip)
        # Jetzt Marker-Anzahl prüfen (nur echte Kandidaten)
        after = len([t for t in tracks if not t.name.startswith(NEW_PREFIX)])
        added = after - len(before_names)
        print(
            f"Threshold {threshold:.3f}: {added} neue Marker (insgesamt {after})",
            flush=True,
        )
        lower_bound = int(target_markers * 0.8)
        upper_bound = int(target_markers * 1.2)
        if lower_bound <= added <= upper_bound:
            print(
                f"✅ Markeranzahl im Zielbereich ({lower_bound}–{upper_bound}) mit {added} neuen Markern",
                flush=True,
            )
            print_track_lengths(clip)
            move_playhead_to_min_tracks(
                ctx,
                clip,
                MIN_MARKERS if playhead_min_markers is None else playhead_min_markers,
            )
            success = True
            break
        delete_new_tracks(tracks)
        print(f"⚠ {after} Marker – versuche erneut", flush=True)
        old_threshold = threshold
        if added > 0:
            threshold = threshold / (MIN_MARKERS / added)
        else:
            threshold *= 0.5  # Bei 0 neuen Markern aggressiver reduzieren
        threshold = max(min(threshold, 1.0), min_threshold)
        print(
            f"🔁 Threshold angepasst: {old_threshold:.4f} → {threshold:.4f}",
            flush=True,
        )
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
    clip["last_threshold"] = threshold  # Für Monitoring
    return success

def register():
    bpy.utils.register_class(WM_OT_auto_track)


def unregister():
    bpy.utils.unregister_class(WM_OT_auto_track)


if __name__ == "__main__":
    register()
    bpy.ops.wm.auto_track('INVOKE_DEFAULT')





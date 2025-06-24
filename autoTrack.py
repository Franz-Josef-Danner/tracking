import bpy
import ctypes
import time

# Windows-Konsole anzeigen (nur Windows)
ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)

# Parameter für das Segment-Tracking
TIME_SEGMENT_SIZE = 100
MIN_TRACKS_PER_SEGMENT = 20
MIN_TRACK_LENGTH = 15

# Thresholds von stabil bis sensibel
THRESHOLDS = [1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.005, 0.001]


def get_clip_context():
    """Liefert einen Context mit aktivem Clip-Editor und Clip zurück."""
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


def count_reliable_tracks(start, end, tracks):
    """Anzahl der Tracks, die im angegebenen Framebereich lang genug sind."""
    count = 0
    for t in tracks:
        frames = [m.frame for m in t.markers if start <= m.frame <= end]
        if len(frames) >= MIN_TRACK_LENGTH:
            count += 1
    return count


def auto_track_segmented():
    """Führt das automatische Tracking segmentweise aus."""
    ctx = get_clip_context()
    clip = ctx["space_data"].clip
    tracks = clip.tracking.tracks

    frame_start = int(clip.frame_start)
    frame_end = frame_start + int(clip.frame_duration) - 1

    print(f"🚀 Starte Tracking von Frame {frame_start} bis {frame_end}", flush=True)

    for segment_start in range(frame_start, frame_end + 1, TIME_SEGMENT_SIZE):
        segment_end = min(segment_start + TIME_SEGMENT_SIZE - 1, frame_end)
        print(f"\n🔍 Segment {segment_start}-{segment_end}", flush=True)

        current_reliable = count_reliable_tracks(segment_start, segment_end, tracks)
        if current_reliable >= MIN_TRACKS_PER_SEGMENT:
            print(f"✅ Bereits {current_reliable} verlässliche Tracks vorhanden", flush=True)
            continue

        print(f"⚠ Nur {current_reliable} Tracks – Feature Detection beginnt", flush=True)
        segment_time_start = time.time()

        for th in THRESHOLDS:
            print(f"  ➤ Threshold {th:.4f}", flush=True)

            bpy.context.scene.frame_current = segment_start
            num_before = len(tracks)

            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.detect_features(threshold=th)

            new_tracks = tracks[num_before:]
            print(f"    → {len(new_tracks)} neue Marker erkannt", flush=True)

            if new_tracks == 0:
                continue

            print(f"    → Tracking …", flush=True)
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.track_markers(backwards=False, sequence=True)

            # Kurzlebige neue Tracks entfernen
            for t in new_tracks:
                frames = [m.frame for m in t.markers if segment_start <= m.frame <= segment_end]
                if len(frames) < MIN_TRACK_LENGTH:
                    tracks.remove(t)

            updated_reliable = count_reliable_tracks(segment_start, segment_end, tracks)
            print(f"    → {updated_reliable} gültige Tracker", flush=True)

            if updated_reliable >= MIN_TRACKS_PER_SEGMENT:
                print(f"    ✅ Ziel erreicht", flush=True)
                break

        duration = time.time() - segment_time_start
        print(f"⏱ Dauer für Segment: {duration:.2f} Sekunden", flush=True)

    print("\n🎉 Automatisches Tracking abgeschlossen.", flush=True)


if __name__ == "__main__":
    auto_track_segmented()

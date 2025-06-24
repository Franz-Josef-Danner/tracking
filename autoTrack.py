import bpy
import ctypes
import time

# === Windows-Konsole anzeigen (nur Windows) ===
ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)

# === Tracking-Parameter ===
time_segment_size = 100
min_tracks_per_segment = 20
min_track_length = 15

# Absteigend: von stabil → sensibel
threshold_list = [1.0, 0.5, 0.25, 0.1, 0.05, 0.01, 0.005, 0.001]

# === Clip-Editor-Kontext finden ===
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
    raise RuntimeError("❌ Kein aktiver Clip im Motion Tracking Editor gefunden.")

ctx = get_clip_context()
clip = ctx["space_data"].clip
tracking = clip.tracking
tracks = tracking.tracks
frame_start = int(clip.frame_start)
frame_end = int(clip.frame_duration) + frame_start - 1

def count_reliable_tracks(start, end):
    count = 0
    for t in tracks:
        marker_frames = [m.frame for m in t.markers if start <= m.frame <= end]
        if len(marker_frames) >= min_track_length:
            count += 1
    return count

print(f"🚀 Starte Tracking von Frame {frame_start} bis {frame_end}", flush=True)

for segment_start in range(frame_start, frame_end + 1, time_segment_size):
    segment_end = min(segment_start + time_segment_size - 1, frame_end)
    print(f"\n🔍 Segment {segment_start}-{segment_end}", flush=True)

    current_reliable = count_reliable_tracks(segment_start, segment_end)
    if current_reliable >= min_tracks_per_segment:
        print(f"✅ Bereits {current_reliable} verlässliche Tracks vorhanden", flush=True)
        continue

    print(f"⚠ Nur {current_reliable} Tracks – Feature Detection beginnt", flush=True)
    segment_time_start = time.time()

    for threshold in threshold_list:
        print(f"  ➤ Threshold {threshold:.4f}", flush=True)

        bpy.context.scene.frame_current = segment_start
        num_before = len(tracks)

        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.detect_features(threshold=threshold)

        num_after = len(tracks)
        new_tracks = num_after - num_before
        print(f"    → {new_tracks} neue Marker erkannt", flush=True)

        if new_tracks == 0:
            continue

        print(f"    → Tracking …", flush=True)
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.track_markers(backwards=False, sequence=True)

        updated_reliable = count_reliable_tracks(segment_start, segment_end)
        print(f"    → {updated_reliable} gültige Tracker", flush=True)

        if updated_reliable >= min_tracks_per_segment:
            print(f"    ✅ Ziel erreicht", flush=True)
            break

    duration = time.time() - segment_time_start
    print(f"⏱ Dauer für Segment: {duration:.2f} Sekunden", flush=True)

print("\n🎉 Automatisches Tracking abgeschlossen.", flush=True)

import bpy
import ctypes
import time

# Windows-Konsole anzeigen (nur Windows)
ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 1)

# Parameter für das Segment-Tracking
TIME_SEGMENT_SIZE = 100
MIN_TRACKS_PER_SEGMENT = 20
MAX_TRACKS_TOTAL = 21
MIN_TRACK_LENGTH = 15

# Anzahl benötigter Marker pro Segment (90 % von MIN_TRACKS_PER_SEGMENT)
MIN_ACTIVE_TRACKS = max(1, int(MIN_TRACKS_PER_SEGMENT * 0.9))

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


def remove_short_tracks(start, end, tracks, ctx):
    """Entfernt Tracks, die im angegebenen Bereich zu kurz sind."""
    to_remove = []
    for t in list(tracks):
        frames = [m.frame for m in t.markers if start <= m.frame <= end]
        if len(frames) < MIN_TRACK_LENGTH:
            to_remove.append(t)

    removed = 0
    for t in to_remove:
        try:
            tracks.remove(t)
        except AttributeError:
            # Fallback über Operator, falls die Collection keine remove()-Methode kennt
            try:
                with bpy.context.temp_override(**ctx):
                    tracks.active = t
                    bpy.ops.clip.track_remove()
            except Exception:
                pass
        removed += 1

    return removed


def remove_low_quality_tracks(tracks, ctx, max_total=MAX_TRACKS_TOTAL):
    """Entfernt die schlechtesten Tracks, bis nur noch max_total übrig sind."""
    if len(tracks) <= max_total:
        return 0

    # Qualität hier simpel über Track-Länge definiert (kürzere = schlechter).
    sorted_tracks = sorted(tracks, key=lambda t: len(t.markers))
    num_remove = len(tracks) - max_total
    removed = 0
    for t in sorted_tracks[:num_remove]:
        try:
            tracks.remove(t)
        except AttributeError:
            try:
                with bpy.context.temp_override(**ctx):
                    tracks.active = t
                    bpy.ops.clip.track_remove()
            except Exception:
                pass
        removed += 1

    return removed


def count_tracks_on_frame(frame, tracks):
    """Zählt, wie viele Tracks im angegebenen Frame aktiv sind."""
    count = 0
    for t in tracks:
        if any(m.frame == frame for m in t.markers):
            count += 1
    return count


def average_track_length(frame, tracks):
    """Gibt die durchschnittliche Länge aller im Frame aktiven Tracks zurück."""
    lengths = []
    for t in tracks:
        frames = [m.frame for m in t.markers if m.frame <= frame]
        if frame in frames:
            lengths.append(len(frames))
    return sum(lengths) / len(lengths) if lengths else 0.0


def track_segment_frames(start, end, ctx, tracks):
    """Trackt Frame für Frame und gibt Informationen pro Frame aus."""
    for f in range(start, end):
        bpy.context.scene.frame_current = f
        with bpy.context.temp_override(**ctx):
            bpy.ops.clip.track_markers(backwards=False, sequence=False)

        active = count_tracks_on_frame(f + 1, tracks)
        quality = average_track_length(f + 1, tracks)
        print(
            f"        Frame {f + 1}: {active} Tracker aktiv, Qualität {quality:.1f}",
            flush=True,
        )


def track_segment(start, end, ctx, tracks):
    """Trackt ein Segment und entfernt anschließend kurze Tracks."""
    track_segment_frames(start, end, ctx, tracks)

    r = remove_short_tracks(start, end, tracks, ctx)
    if r:
        print(f"    🗑 {r} kurze Tracks entfernt", flush=True)

    updated = count_reliable_tracks(start, end, tracks)
    print(f"    → {updated} gültige Tracker", flush=True)
    return updated


def auto_track_segmented():
    """Führt das automatische Tracking segmentweise aus."""
    ctx = get_clip_context()
    clip = ctx["space_data"].clip
    tracks = clip.tracking.tracks

    frame_start = int(clip.frame_start)
    frame_end = frame_start + int(clip.frame_duration) - 1

    print(f"🚀 Starte Tracking von Frame {frame_start} bis {frame_end}", flush=True)

    threshold_idx = 0

    for segment_start in range(frame_start, frame_end + 1, TIME_SEGMENT_SIZE):
        segment_end = min(segment_start + TIME_SEGMENT_SIZE - 1, frame_end)
        print(f"\n🔍 Segment {segment_start}-{segment_end}", flush=True)

        removed = remove_short_tracks(segment_start, segment_end, tracks, ctx)
        if removed:
            print(f"🗑 {removed} kurze Tracks entfernt", flush=True)

        current_active = count_tracks_on_frame(segment_start, tracks)
        segment_time_start = time.time()

        if current_active >= MIN_ACTIVE_TRACKS:
            print(
                f"✅ Bereits {current_active} Marker aktiv",
                flush=True,
            )
        else:
            print(
                f"⚠ Nur {current_active} Tracks – Feature Detection beginnt",
                flush=True,
            )
            while current_active < MIN_ACTIVE_TRACKS:
                th = THRESHOLDS[threshold_idx]
                print(f"  ➤ Threshold {th:.4f}", flush=True)

                bpy.context.scene.frame_current = segment_start
                num_before = len(tracks)

                with bpy.context.temp_override(**ctx):
                    bpy.ops.clip.detect_features(threshold=th)

                new_tracks = tracks[num_before:]
                print(f"    → {len(new_tracks)} neue Marker erkannt", flush=True)
                current_active = count_tracks_on_frame(segment_start, tracks)

                if current_active >= MIN_ACTIVE_TRACKS:
                    break
                if threshold_idx < len(THRESHOLDS) - 1:
                    threshold_idx += 1
                else:
                    break

        print("    → Tracking …", flush=True)
        bpy.context.scene.frame_current = segment_start
        updated_reliable = track_segment(
            segment_start, segment_end, ctx, tracks
        )

        if updated_reliable >= MIN_TRACKS_PER_SEGMENT:
            print(f"    ✅ Ziel erreicht", flush=True)
            threshold_idx = 0
        else:
            print("    ❌ Ziel nicht erreicht", flush=True)

        duration = time.time() - segment_time_start
        print(f"⏱ Dauer für Segment: {duration:.2f} Sekunden", flush=True)

    # Gesamte Anzahl prüfen und ggf. schlechteste Tracks entfernen
    removed_total = remove_low_quality_tracks(tracks, ctx, MAX_TRACKS_TOTAL)
    if removed_total:
        print(f"\n🗑 {removed_total} minderwertige Tracks entfernt, um auf {MAX_TRACKS_TOTAL} zu begrenzen", flush=True)

    print("\n🎉 Automatisches Tracking abgeschlossen.", flush=True)


if __name__ == "__main__":
    auto_track_segmented()

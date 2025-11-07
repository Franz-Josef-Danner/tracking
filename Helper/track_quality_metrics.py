import bpy
import math

def _count_spikes_for_track(track, velocity_thresh=0.008, accel_thresh=0.020):
    """Ermittelt Spike-Zahlen (Velocity/Accel) ohne Konsolen-Logs."""
    ms = sorted([m for m in track.markers if not m.mute], key=lambda m: m.frame)
    if len(ms) < 3:
        return 0, 0, 0

    spikes = 0
    vel_spikes = 0
    acc_spikes = 0

    def vec(a, b):
        return (b.co[0] - a.co[0], b.co[1] - a.co[1])

    prev_v = None

    for i in range(1, len(ms)):
        v = vec(ms[i - 1], ms[i])
        v_len = math.hypot(*v)

        if v_len > velocity_thresh:
            vel_spikes += 1
            spikes += 1

        if prev_v is not None:
            a_vec = (v[0] - prev_v[0], v[1] - prev_v[1])
            a_len = math.hypot(*a_vec)
            if a_len > accel_thresh:
                acc_spikes += 1
                spikes += 1

        prev_v = v

    return spikes, vel_spikes, acc_spikes


def compute_track_quality_metrics(
    context: bpy.types.Context,
    *,
    min_len_for_long=25,
    velocity_thresh=0.004,
    accel_thresh=0.003,
    spike_density_threshold=5.0,  # Spikes pro 100 Frames
):
    """
    Bewertet die Trackingqualität (ohne Log-Ausgaben):
    - Nur aktive (nicht gemutete) Marker werden berücksichtigt.
    - Segmentlänge = max(frame) - min(frame) + 1 (aus aktiven Markern)
    - Schwelle für "lang" wird dynamisch aus scene.max_error_value genommen (Fallback: min_len_for_long).
    - Spike-Dichte in Spikes pro 100 Frames.
    - Prozent = Anteil sauberer, langer Tracks an allen Tracks.
    """
    # Dynamische Mindestlänge aus Szene holen
    try:
        scene = context.scene
        dyn_val = getattr(scene, "max_error_value", None)
        if dyn_val is None:
            raise ValueError("scene.max_error_value fehlt")
        dyn_float = float(dyn_val)
        if not math.isfinite(dyn_float) or dyn_float <= 0:
            raise ValueError("scene.max_error_value ungültig")
        min_len_for_long = max(1, int(math.floor(dyn_float)))
    except Exception:
        min_len_for_long = max(1, int(math.floor(min_len_for_long)))

    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip if getattr(context, "space_data", None) and getattr(context.space_data, "type", None) == "CLIP_EDITOR" else None
    )
    if clip is None or not hasattr(clip, "tracking"):
        return {"anzahl_alle_tracks": 0, "prozent": 0.0}

    # 1) Alle Tracks mit aktiven Markern
    alle_tracks = [t for t in clip.tracking.tracks if any(not m.mute for m in t.markers)]
    anzahl_alle_tracks = len(alle_tracks)

    # 2) Länge jedes Tracks und Ermittlung kurzer Tracks
    unter_25 = []
    for t in alle_tracks:
        active_frames = [m.frame for m in t.markers if not m.mute]
        if not active_frames:
            continue
        seg_len = (max(active_frames) - min(active_frames)) + 1
        if seg_len < min_len_for_long:
            unter_25.append(t)

    anzahl_unter_25 = len(unter_25)

    # 3) Lange Tracks
    anzahl_lange_tracks = max(0, anzahl_alle_tracks - anzahl_unter_25)

    # 4) Spike-Erkennung & Spike-Dichte
    spike_tracks = []
    for t in alle_tracks:
        spikes, _, _ = _count_spikes_for_track(
            t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh
        )
        active_frames = [m.frame for m in t.markers if not m.mute]
        if active_frames:
            seg_len = (max(active_frames) - min(active_frames)) + 1
        else:
            seg_len = 0

        if seg_len > 0:
            spike_density = (spikes / seg_len) * 100.0
        else:
            spike_density = 0.0

        if spike_density >= spike_density_threshold:
            spike_tracks.append(t)

    anzahl_spike_tracks = len(spike_tracks)

    # 5) Saubere Tracks & Prozent
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)
    if anzahl_alle_tracks < 1:
        prozent = 0.0
    else:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

    return {
        "anzahl_alle_tracks": anzahl_alle_tracks,
        "anzahl_unter_25": anzahl_unter_25,
        "anzahl_lange_tracks": anzahl_lange_tracks,
        "anzahl_spike_tracks": anzahl_spike_tracks,
        "saubere_tracks": saubere_tracks,
        "prozent": prozent,
    }

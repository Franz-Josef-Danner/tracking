import bpy
import math

def _count_spikes_for_track(track, velocity_thresh=0.008, accel_thresh=0.020):
    """Einfache Spike-Heuristik."""
    ms = sorted(track.markers, key=lambda m: m.frame)
    if len(ms) < 3:
        return 0
    spikes = 0
    def vec(a, b):
        return (b.co[0]-a.co[0], b.co[1]-a.co[1])
    prev_v = None
    for i in range(1, len(ms)):
        v = vec(ms[i-1], ms[i])
        v_len = math.hypot(*v)
        if v_len > velocity_thresh:
            spikes += 1
        if prev_v is not None:
            a_vec = (v[0]-prev_v[0], v[1]-prev_v[1])
            a_len = math.hypot(*a_vec)
            if a_len > accel_thresh:
                spikes += 1
        prev_v = v
    return spikes


def compute_track_quality_metrics(context: bpy.types.Context,
                                  *,
                                  min_len_for_long=25,
                                  spike_threshold=20,
                                  velocity_thresh=0.008,
                                  accel_thresh=0.020):

    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip
        if context.space_data and context.space_data.type == 'CLIP_EDITOR'
        else None
    )
    if clip is None:
        return {"alle_tracks": [], "anzahl_alle_tracks": 0, "unter_25": [], "anzahl_unter_25": 0,
                "anzahl_lange_tracks": 0, "spike_tracks": [], "anzahl_spike_tracks": 0,
                "saubere_tracks": 0, "prozent": 0.0}

    alle_tracks = list(clip.tracking.tracks)
    anzahl_alle_tracks = len(alle_tracks)
    print(f"[Quality] Gesamtanzahl Tracks: {anzahl_alle_tracks}")

    # --- Tracklängen einmalig berechnen ---
    track_lengths = {}
    for t in alle_tracks:
        if not t.markers:
            track_lengths[t.name] = 0
            continue
        frames = [m.frame for m in t.markers]
        length = (max(frames) - min(frames)) + 1
        track_lengths[t.name] = length
        print(f"[Quality][Len] Track='{t.name}' Framespan={min(frames)}..{max(frames)} Len={length}")

    # --- Auswerten ---
    unter_25 = [t for t in alle_tracks if track_lengths[t.name] < min_len_for_long]
    anzahl_unter_25 = len(unter_25)

    lange_tracks = [t for t in alle_tracks if track_lengths[t.name] >= min_len_for_long]
    anzahl_lange_tracks = len(lange_tracks)
    print(f"[Quality] Kurz(<{min_len_for_long}f)={anzahl_unter_25} | Lang(≥{min_len_for_long}f)={anzahl_lange_tracks}")

    # --- Spike-Zählung ---
    spike_tracks = []
    for t in lange_tracks:
        spikes = _count_spikes_for_track(t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh)
        if spikes > spike_threshold:
            spike_tracks.append(t)
        print(f"[Quality][Spikes] Track='{t.name}' Spikes={spikes} "
              f"(Thresh>{spike_threshold} ⇒ {'FLAG' if spikes > spike_threshold else 'ok'})")

    anzahl_spike_tracks = len(spike_tracks)
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)
    print(f"[Quality] Spiky={anzahl_spike_tracks} | Sauber(Lang−Spiky)={saubere_tracks}")

    # --- Qualitätsmetrik ---
    prozent = 0.0
    if anzahl_alle_tracks > 0:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

    print(f"[Quality][Metric] Alle={anzahl_alle_tracks} | Sauber={saubere_tracks} "
          f"| Prozent={prozent:.2f}%  (Formel: 100/Alle*Sauber)")

    return {
        "alle_tracks": alle_tracks,
        "anzahl_alle_tracks": anzahl_alle_tracks,
        "unter_25": unter_25,
        "anzahl_unter_25": anzahl_unter_25,
        "anzahl_lange_tracks": anzahl_lange_tracks,
        "spike_tracks": spike_tracks,
        "anzahl_spike_tracks": anzahl_spike_tracks,
        "saubere_tracks": saubere_tracks,
        "prozent": prozent,
    }

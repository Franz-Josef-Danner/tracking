# Helper/track_quality_metrics.py
import bpy
import math

def _count_spikes_for_track(track, velocity_thresh=0.008, accel_thresh=0.020):
    """
    Sehr einfache Spike-Heuristik:
    - velocity spike: Sprung zwischen aufeinanderfolgenden Markern > velocity_thresh (Norm in Clip-Koordinaten 0..1)
    - accel spike:    starke Richtungs-/Geschwindigkeitsänderung (Zweite Ableitung) > accel_thresh
    Rückgabe: int (Spike-Count)
    """
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


def compute_track_quality_metrics(context: bpy.types.Context):
    """
    Algorithmus nach vorgegebener Logik:
      alle_tracks = bpy.ops.clip.select_all(*, action='TOGGLE')
      anzahl_alle_tracks = menge der alle_tracks
      unter_25 = bpy.ops.clip.clean_tracks(*, frames=25, error=0.0, action='SELECT')
      anzahl_unter_25 = menge der unter_25
      anzahl_lange_tracks = anzahl_alle_tracks - anzahl_unter_25
      spike_tracks = tracks mit mehr als 5 spike error
      anzahl_spike_tracks = menge der spike_tracks
      saubere_tracks = anzahl_lange_tracks - anzahl_spike_tracks
      wenn anzahl_alle_tracks < 1 → prozent = 0
      sonst → prozent = (100 / anzahl_alle_tracks) * saubere_tracks
    """
    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip if context.space_data and context.space_data.type == 'CLIP_EDITOR' else None
    )
    if clip is None:
        return {
            "alle_tracks": [],
            "anzahl_alle_tracks": 0,
            "unter_25": [],
            "anzahl_unter_25": 0,
            "anzahl_lange_tracks": 0,
            "spike_tracks": [],
            "anzahl_spike_tracks": 0,
            "saubere_tracks": 0,
            "prozent": 0.0,
        }

    # Alle Tracks im Clip
    alle_tracks = list(clip.tracking.tracks)
    anzahl_alle_tracks = len(alle_tracks)

    # Unter-25-Filter (simuliert bpy.ops.clip.clean_tracks(frames=25))
    unter_25 = []
    for t in alle_tracks:
        if len(t.markers) < 2:
            continue
        frames = [m.frame for m in t.markers]
        if (max(frames) - min(frames)) + 1 < 25:
            unter_25.append(t)
    anzahl_unter_25 = len(unter_25)

    # Lange Tracks = alle - kurze
    anzahl_lange_tracks = anzahl_alle_tracks - anzahl_unter_25
    lange_tracks = [t for t in alle_tracks if t not in unter_25]

    # Spike-Analyse
    spike_tracks = []
    for t in lange_tracks:
        spikes = _count_spikes_for_track(t)
        if spikes > 5:
            spike_tracks.append(t)
    anzahl_spike_tracks = len(spike_tracks)

    # Saubere Tracks = lange - spiky
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)

    # Prozentberechnung
    if anzahl_alle_tracks < 1:
        prozent = 0.0
    else:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

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

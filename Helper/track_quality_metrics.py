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
    # Vorwärts-Differenzen
    def vec(a, b):
        return (b.co[0]-a.co[0], b.co[1]-a.co[1])

    prev_v = None
    for i in range(1, len(ms)):
        v = vec(ms[i-1], ms[i])
        v_len = math.hypot(*v)
        if v_len > velocity_thresh:
            spikes += 1
        if prev_v is not None:
            # „Beschleunigung“ als Änderung des Bewegungsvektors
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
    """
    Führt Qualitätsbewertung exakt nach spezifiziertem Ablauf aus.
    """
    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip if context.space_data and context.space_data.type == "CLIP_EDITOR" else None
    )

    if clip is None or not hasattr(clip, "tracking"):
        print("[Quality] ❌ Kein aktiver Clip oder Tracking-Daten vorhanden.")
        return {"anzahl_alle_tracks": 0, "prozent": 0.0}

    # ------------------------------------------------------------
    # 1. Alle Tracks zählen
    # ------------------------------------------------------------
    alle_tracks = list(clip.tracking.tracks)
    anzahl_alle_tracks = len(alle_tracks)
    print(f"[Quality] 🟢 Alle Tracks: {anzahl_alle_tracks}")

    # ------------------------------------------------------------
    # 2. Unter-25-Frames-Tracks selektieren via clean_tracks (Simulation)
    # ------------------------------------------------------------
    unter_25 = []
    for t in alle_tracks:
        frames = [m.frame for m in t.markers]
        if not frames:
            continue
        length = (max(frames) - min(frames)) + 1
        if length < min_len_for_long:
            unter_25.append(t)
    anzahl_unter_25 = len(unter_25)
    print(f"[Quality] 🟡 Tracks unter 25 Frames: {anzahl_unter_25}")

    # ------------------------------------------------------------
    # 3. Lange Tracks (alle - unter_25)
    # ------------------------------------------------------------
    anzahl_lange_tracks = max(0, anzahl_alle_tracks - anzahl_unter_25)
    print(f"[Quality] 🔵 Lange Tracks: {anzahl_lange_tracks}")

    # ------------------------------------------------------------
    # 4. Spike-Erkennung (mehr als 5 Spikes)
    # ------------------------------------------------------------
    spike_tracks = []
    for t in alle_tracks:
        spikes = _count_spikes_for_track(t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh)
        if spikes > 5:
            spike_tracks.append(t)
            print(f"[Quality] ⚠️ SpikeTrack: '{t.name}' mit {spikes} Spikes")

    anzahl_spike_tracks = len(spike_tracks)
    print(f"[Quality] 🧨 Tracks mit >5 Spikes: {anzahl_spike_tracks}")

    # ------------------------------------------------------------
    # 5. Saubere Tracks
    # ------------------------------------------------------------
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)
    print(f"[Quality] 🧩 Saubere Tracks: {saubere_tracks}")

    # ------------------------------------------------------------
    # 6. Prozentberechnung
    # ------------------------------------------------------------
    if anzahl_alle_tracks < 1:
        prozent = 0.0
    else:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

    print(f"[Quality] 🎯 Endergebnis: {prozent:.2f}%")

    return {
        "anzahl_alle_tracks": anzahl_alle_tracks,
        "anzahl_unter_25": anzahl_unter_25,
        "anzahl_lange_tracks": anzahl_lange_tracks,
        "anzahl_spike_tracks": anzahl_spike_tracks,
        "saubere_tracks": saubere_tracks,
        "prozent": prozent,
    }

    alle_tracks = list(clip.tracking.tracks)
    anzahl_alle_tracks = len(alle_tracks)

    # Track-Länge in Frames bestimmen (inkl. Lücken-tolerant: min/max Marker-Frame)
    def track_len_frames(t):
        if not t.markers:
            return 0
        frames = [m.frame for m in t.markers]
        return (max(frames) - min(frames)) + 1

    unter_25 = [t for t in alle_tracks if track_len_frames(t) < min_len_for_long]
    anzahl_unter_25 = len(unter_25)

    lange_tracks = [t for t in alle_tracks if track_len_frames(t) >= min_len_for_long]
    anzahl_lange_tracks = len(lange_tracks)

    spike_tracks = []
    for t in lange_tracks:
        spikes = _count_spikes_for_track(t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh)
        if spikes > spike_threshold:
            spike_tracks.append(t)

    anzahl_spike_tracks = len(spike_tracks)
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)

    # ------------------------------------------------------------
    # Ursprungslogik mit klarer Null- und Randfallbehandlung
    # ------------------------------------------------------------
    if anzahl_alle_tracks == 0:
        prozent = 0.0
    else:
        # Prozentwert nach Ursprungsformel
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks
        # Wenn keine sauberen langen Tracks existieren → 0 %
        if saubere_tracks == 0 or anzahl_lange_tracks == 0:
            prozent = 0.0
        else:
            # Clamping
            prozent = max(0.0, min(100.0, prozent))
            # Nur wenn wirklich alle langen Tracks sauber sind UND
            # alle langen Tracks = alle Tracks (keine kurzen) → 100 %
            if not (anzahl_lange_tracks == saubere_tracks and anzahl_lange_tracks == anzahl_alle_tracks):
                # Sicherstellen, dass kein Rundungsartefakt zu 100 % führt
                if prozent >= 99.5:
                    prozent = 99.0

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

# Helper/track_quality_metrics.py
import bpy
import math


def _count_spikes_for_track(track, velocity_thresh=0.008, accel_thresh=0.020):
    """Zählt Bewegungsspitzen (Spikes) im Track basierend auf Markerpositionen."""
    ms = sorted([m for m in track.markers if not m.mute], key=lambda m: m.frame)
    if len(ms) < 3:
        print(f"[Spikes] ⚪ Track '{track.name}' zu kurz ({len(ms)} Marker) – übersprungen.")
        return 0

    spikes = 0
    vel_spikes = 0
    acc_spikes = 0

    def vec(a, b):
        return (b.co[0] - a.co[0], b.co[1] - a.co[1])

    prev_v = None
    for i in range(1, len(ms)):
        v = vec(ms[i - 1], ms[i])
        v_len = math.hypot(*v)

        # Velocity Spike
        if v_len > velocity_thresh:
            spikes += 1
            vel_spikes += 1
            print(f"[Spikes][{track.name}] 🚀 Velocity Spike bei Frame {ms[i].frame}: Δ={v_len:.4f}")

        # Acceleration Spike
        if prev_v is not None:
            a_vec = (v[0] - prev_v[0], v[1] - prev_v[1])
            a_len = math.hypot(*a_vec)
            if a_len > accel_thresh:
                spikes += 1
                acc_spikes += 1
                print(f"[Spikes][{track.name}] 💥 Accel Spike bei Frame {ms[i].frame}: Δ={a_len:.4f}")

        prev_v = v

    print(
        f"[Spikes][{track.name}] 🔹 Gesamt: {spikes} (Velocity={vel_spikes}, Accel={acc_spikes}) "
        f"bei {len(ms)} aktiven Markern."
    )
    return spikes


def compute_track_quality_metrics(
    context: bpy.types.Context,
    *,
    min_len_for_long=25,
    spike_threshold=0.005,
    velocity_thresh=0.002,
    accel_thresh=0.005,
):
    """
    Bewertet die Trackingqualität:
    - Nur aktive (nicht gemutete) Marker werden berücksichtigt.
    - Segmentlänge = max(frame) - min(frame) + 1 (aus aktiven Markern)
    - Tracks unter 25 Frames gelten als "kurz".
    - Tracks mit >3 Spikes gelten als instabil.
    - Prozent = Anteil sauberer, langer Tracks an allen Tracks.
    """
    clip = getattr(context, "edit_movieclip", None) or (
        context.space_data.clip if context.space_data and context.space_data.type == "CLIP_EDITOR" else None
    )
    if clip is None or not hasattr(clip, "tracking"):
        print("[Quality] ❌ Kein aktiver Clip oder Tracking-Daten vorhanden.")
        return {"anzahl_alle_tracks": 0, "prozent": 0.0}

    # ------------------------------------------------------------
    # 1. Alle Tracks mit aktiven Markern
    # ------------------------------------------------------------
    alle_tracks = [t for t in clip.tracking.tracks if any(not m.mute for m in t.markers)]
    anzahl_alle_tracks = len(alle_tracks)
    print(f"[Quality] 🟢 Alle aktiven Tracks: {anzahl_alle_tracks}")

    # ------------------------------------------------------------
    # 2. Länge jedes Tracks (nur aktive Marker)
    # ------------------------------------------------------------
    unter_25 = []
    for t in alle_tracks:
        active_frames = [m.frame for m in t.markers if not m.mute]
        if not active_frames:
            continue
        seg_len = (max(active_frames) - min(active_frames)) + 1
        print(f"[Quality] 📏 Track '{t.name}' aktive Segmentlänge: {seg_len}")
        if seg_len < min_len_for_long:
            unter_25.append(t)

    anzahl_unter_25 = len(unter_25)
    print(f"[Quality] 🟡 Unter 25 Frames: {anzahl_unter_25}")

    # ------------------------------------------------------------
    # 3. Lange Tracks
    # ------------------------------------------------------------
    anzahl_lange_tracks = max(0, anzahl_alle_tracks - anzahl_unter_25)
    print(f"[Quality] 🔵 Lange Tracks: {anzahl_lange_tracks}")

    # ------------------------------------------------------------
    # 4. Spike-Erkennung (mehr als 3 Spikes)
    # ------------------------------------------------------------
    spike_tracks = []
    for t in alle_tracks:
        spikes = _count_spikes_for_track(t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh)
        if spikes > spike_threshold:
            spike_tracks.append(t)
            print(f"[Quality] ⚠️ SpikeTrack '{t.name}' mit {spikes} Spikes (>{spike_threshold})")

    anzahl_spike_tracks = len(spike_tracks)
    print(f"[Quality] 🧨 Tracks mit >{spike_threshold} Spikes: {anzahl_spike_tracks}")

    # ------------------------------------------------------------
    # 5. Saubere Tracks und Prozent
    # ------------------------------------------------------------
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)
    print(f"[Quality] 🧩 Saubere Tracks: {saubere_tracks}")

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

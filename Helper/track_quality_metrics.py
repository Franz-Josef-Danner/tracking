import bpy
import math

def _count_spikes_for_track(track, velocity_thresh=0.008, accel_thresh=0.020):
    """Gibt rohe Bewegungsdaten (Velocity/Accel) pro Frame aus – Schwellen nur informativ."""
    ms = sorted([m for m in track.markers if not m.mute], key=lambda m: m.frame)
    if len(ms) < 3:
        print(f"[Spikes] ⚪ Track '{track.name}' zu kurz ({len(ms)} Marker) – übersprungen.")
        return 0, 0, 0

    spikes = 0
    vel_spikes = 0
    acc_spikes = 0

    def vec(a, b):
        return (b.co[0] - a.co[0], b.co[1] - a.co[1])

    prev_v = None
    print(f"\n[Spikes][{track.name}] ───── Rohdatenanalyse ─────")
    print(f"   • Velocity Threshold (log only): {velocity_thresh:.6f}")
    print(f"   • Accel Threshold    (log only): {accel_thresh:.6f}")
    print("──────────────────────────────────────────────")

    for i in range(1, len(ms)):
        v = vec(ms[i - 1], ms[i])
        v_len = math.hypot(*v)

        # Immer loggen
        msg = f"Frame {ms[i].frame:4d} | ΔV={v_len:.6f}"
        if v_len > velocity_thresh:
            vel_spikes += 1
            spikes += 1
            msg += "  🚀 >VEL"
        print(msg)

        # Acceleration immer berechnen
        if prev_v is not None:
            a_vec = (v[0] - prev_v[0], v[1] - prev_v[1])
            a_len = math.hypot(*a_vec)
            msg_a = f"         ΔA={a_len:.6f}"
            if a_len > accel_thresh:
                acc_spikes += 1
                spikes += 1
                msg_a += "  💥 >ACC"
            print(msg_a)

        prev_v = v

    # --- Abschließende Übersicht ---
    print(f"[Spikes][{track.name}] 🔹 Gesamtübersicht:")
    print(f"    • Velocity-Spikes : {vel_spikes}")
    print(f"    • Accel-Spikes    : {acc_spikes}")
    print(f"    • Gesamt-Spikes   : {spikes}")
    print(f"    • Aktive Marker   : {len(ms)}")
    print("──────────────────────────────────────────────")

    return spikes, vel_spikes, acc_spikes

def compute_track_quality_metrics(
    context: bpy.types.Context,
    *,
    min_len_for_long=25,
    spike_threshold=0.012,
    velocity_thresh=0.020,
    accel_thresh=0.050,
):
    """
    Bewertet die Trackingqualität:
    - Nur aktive (nicht gemutete) Marker werden berücksichtigt.
    - Segmentlänge = max(frame) - min(frame) + 1 (aus aktiven Markern)
    - Tracks unter 25 Frames gelten als "kurz".
    - Schwelle für "kurz" wird dynamisch aus scene.max_error_value genommen (Fallback 25).
    - Tracks mit >3 Spikes gelten als instabil.
    - Prozent = Anteil sauberer, langer Tracks an allen Tracks.
    """
    # --- Dynamische Mindestlänge aus Szene holen ---------------------------------
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
    # 2. Länge jedes Tracks
    # ------------------------------------------------------------
    unter_25 = []
    for t in alle_tracks:
        active_frames = [m.frame for m in t.markers if not m.mute]
        if not active_frames:
            continue
        seg_len = (max(active_frames) - min(active_frames)) + 1
        if seg_len < min_len_for_long:
            unter_25.append(t)
        print(f"[Quality] 📏 Track '{t.name}' Segmentlänge: {seg_len}")

    anzahl_unter_25 = len(unter_25)
    print(f"[Quality] 🟡 Unter {min_len_for_long} Frames: {anzahl_unter_25}")

    # ------------------------------------------------------------
    # 3. Lange Tracks
    # ------------------------------------------------------------
    anzahl_lange_tracks = max(0, anzahl_alle_tracks - anzahl_unter_25)
    print(f"[Quality] 🔵 Lange Tracks (≥ {min_len_for_long}): {anzahl_lange_tracks}")

    # ------------------------------------------------------------
    # 4. Spike-Erkennung
    # ------------------------------------------------------------
    spike_tracks = []
    for t in alle_tracks:
        spikes, vel_spikes, acc_spikes = _count_spikes_for_track(
            t, velocity_thresh=velocity_thresh, accel_thresh=accel_thresh
        )
        if spikes > spike_threshold:
            spike_tracks.append(t)
            print(f"[Quality] ⚠️ SpikeTrack '{t.name}' mit {spikes} Spikes (>{spike_threshold})")

    anzahl_spike_tracks = len(spike_tracks)
    print(f"[Quality] 🧨 Tracks mit >{spike_threshold} Spikes: {anzahl_spike_tracks}")

    # ------------------------------------------------------------
    # 5. Saubere Tracks & Prozent
    # ------------------------------------------------------------
    saubere_tracks = max(0, anzahl_lange_tracks - anzahl_spike_tracks)
    if anzahl_alle_tracks < 1:
        prozent = 0.0
    else:
        prozent = (100.0 / anzahl_alle_tracks) * saubere_tracks

    print(f"[Quality] 🧩 Saubere Tracks: {saubere_tracks}")
    print(f"[Quality] 🎯 Endergebnis: {prozent:.2f}%")
    print("══════════════════════════════════════════════════════")

    return {
        "anzahl_alle_tracks": anzahl_alle_tracks,
        "anzahl_unter_25": anzahl_unter_25,
        "anzahl_lange_tracks": anzahl_lange_tracks,
        "anzahl_spike_tracks": anzahl_spike_tracks,
        "saubere_tracks": saubere_tracks,
        "prozent": prozent,
    }

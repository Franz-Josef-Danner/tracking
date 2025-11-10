# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# ID-basierte Version – kompatibel mit "good_track_ids" / "best_track_ids"
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple
import bpy

# ----------------------------
# Low-level Marker Utilities
# ----------------------------

def _find_marker_at_frame(track, frame):
    try:
        mk = track.markers.find_frame(frame)
        return mk if mk and not mk.mute else None
    except Exception:
        return None

def marker_exists(track, frame):
    return _find_marker_at_frame(track, frame) is not None

def get_marker_position(track, frame):
    mk = _find_marker_at_frame(track, frame)
    if mk:
        return float(mk.co[0]), float(mk.co[1])
    head = track.markers[0] if track.markers else None
    return (float(head.co[0]), float(head.co[1])) if head else (0.0, 0.0)

def set_marker_position(track, frame, x, y):
    mk = _find_marker_at_frame(track, frame)
    if mk:
        mk.co[0] = float(x)
        mk.co[1] = float(y)

def _active_clip(context):
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None

def _iter_active_tracks_at_frame(context, frame):
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr

def get_active_markers(context, frame):
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))


# ----------------------------
# Core Correction (ID-basiert)
# ----------------------------

def _select_good_set(scene):
    """Wählt das aktive Set aus der Szene und erkennt automatisch ID- oder Namenlisten."""
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene
    if has_good and has_best:
        print("[MarkerCalib] ❌ Konflikt: Sowohl 'good_tracks' als auch 'best_tracks' vorhanden.")
        return None, None

    key = None
    if has_good:
        key = "good_tracks"
    elif has_best:
        key = "best_tracks"

    if key is None:
        print("[MarkerCalib] ⚠️ Kein gültiges Referenzset vorhanden")
        return None, None

    raw = list(scene[key])
    # Erkennen: enthält IDs (Strings mit nur Ziffern) oder Namen
    is_id_based = all(isinstance(v, str) and v.isdigit() for v in raw)
    print(f"[MarkerCalib] ✅ Verwende '{key}'-Set ({len(raw)} Einträge, {'ID' if is_id_based else 'Name'}-basiert)")
    return raw, is_id_based


def correct_marker_positions(context, selected_tracks, frame_a, frame_b, frame_c=None, frame_d=None):
    print("\n[MarkerCalib] ---- Starte Marker-Korrektur ----")
    print(f"[MarkerCalib] Frames: A={frame_a}, B={frame_b}, C={frame_c}, D={frame_d}")
    print(f"[MarkerCalib] Selektierte Marker (input): {len(selected_tracks)}")

    scene = context.scene
    clip = _active_clip(context)
    if not clip:
        print("[MarkerCalib] ❌ Kein aktiver Clip – Abbruch.")
        return

    print(f"[MarkerCalib] Aktiver Clip: {clip.name}")
    good_values, id_based = _select_good_set(scene)
    if not good_values:
        print("[MarkerCalib] ❌ Abbruch – kein valider Referenzsatz.")
        return

    # --- Aufbau des Referenzsets ---
    all_tracks = list(clip.tracking.tracks)

    if id_based:
        good_tracks = [t for t in all_tracks if str(id(t)) in good_values]
        missing = [gid for gid in good_values if gid not in [str(id(t)) for t in good_tracks]]
    else:
        name_to_track = {t.name: t for t in all_tracks}
        good_tracks = [name_to_track[n] for n in good_values if n in name_to_track]
        missing = [n for n in good_values if n not in name_to_track]

    print(f"[MarkerCalib] Aufgelöste Tracks: {len(good_tracks)}  Fehlende: {len(missing)}")
    if missing:
        print(f"[MarkerCalib] Fehlende Beispiele: {missing[:5]}")

    # --- Diagnose zu Selektion ---
    all_sel_names = [t.name for t in selected_tracks]
    if id_based:
        sel_ids = [str(id(t)) for t in selected_tracks]
        intersect = [sid for sid in sel_ids if sid in good_values]
        diff = [sid for sid in sel_ids if sid not in good_values]
    else:
        intersect = [n for n in all_sel_names if n in good_values]
        diff = [n for n in all_sel_names if n not in good_values]

    print(f"[MarkerCalib] Vergleich Selektierte vs Referenz:")
    print(f"   - Selektiert: {len(selected_tracks)}")
    print(f"   - Im Referenz-Set: {len(intersect)}")
    print(f"   - Nicht im Referenz-Set: {len(diff)}")
    if intersect:
        print(f"   - Beispiele im Schnitt: {intersect[:5]}")
    if diff:
        print(f"   - Beispiele außerhalb: {diff[:5]}")

    # --- Frameweise Markerprüfung ---
    frames = [frame_a, frame_b, frame_c, frame_d]
    labels = ["A", "B", "C", "D"]
    for lbl, f in zip(labels, frames):
        if f is None:
            continue
        frame_tracks = get_active_markers(context, f)
        print(f"[MarkerCalib] Frame {lbl}({f}): {len(frame_tracks)} aktive Marker")
        if frame_tracks:
            print("   → Namen:", [t.name for t in frame_tracks][:10])
        else:
            print("   → Keine aktiven Marker")
        # Überprüfung im good_set
        if id_based:
            in_good = [t for t in frame_tracks if str(id(t)) in good_values]
        else:
            in_good = [t for t in frame_tracks if t.name in good_values]
        print(f"   → {len(in_good)} dieser Marker auch im Referenzset")

    # Existierende Marker im Referenzset (unabhängig von Auswahl)
    def _count_exist(tracks, f): return sum(1 for t in tracks if marker_exists(t, f))
    for lbl, f in zip(labels, frames):
        if f is None:
            continue
        cnt = _count_exist(good_tracks, f)
        print(f"[MarkerCalib] Existierende Referenzmarker @ {lbl}({f}): {cnt}")

    # --- Aktive Marker pro Frame ---
    fa_marker = get_active_markers(context, frame_a)
    fb_marker = get_active_markers(context, frame_b)
    fc_marker = get_active_markers(context, frame_c) if frame_c else []
    fd_marker = get_active_markers(context, frame_d) if frame_d else []

    # Diagnose: Objekt-Identität prüfen
    if fa_marker and good_tracks:
        overlap = sum(1 for m in fa_marker for g in good_tracks if m is g)
        print(f"[MarkerCalib] FrameA Objekt-Identität mit Referenz: {overlap}/{len(fa_marker)}")

    # Filterung je Frame
    if id_based:
        fa_good = [m for m in fa_marker if str(id(m)) in good_values]
        fb_good = [m for m in fb_marker if str(id(m)) in good_values]
        fc_good = [m for m in fc_marker if str(id(m)) in good_values]
        fd_good = [m for m in fd_marker if str(id(m)) in good_values]
    else:
        fa_good = [m for m in fa_marker if m.name in good_values]
        fb_good = [m for m in fb_marker if m.name in good_values]
        fc_good = [m for m in fc_marker if m.name in good_values]
        fd_good = [m for m in fd_marker if m.name in good_values]

    print(f"[MarkerCalib] Gute Marker je Frame:")
    print(f"   A={len(fa_good)}  B={len(fb_good)}  C={len(fc_good)}  D={len(fd_good)}")

    # Diagnose bei leerem Ergebnis
    if sum(len(x) for x in (fa_good, fb_good, fc_good, fd_good)) == 0:
        print("[MarkerCalib][DIAG] Kein Frame mit Übereinstimmung gefunden!")
        if fa_marker:
            example = fa_marker[0]
            print(f"[MarkerCalib][DIAG] Beispielmarker: {example.name}, Typ={type(example)}")
            if id_based:
                exists = str(id(example)) in good_values
                print(f"[MarkerCalib][DIAG] Existiert im Referenzset (ID)? {exists}")
                print(f"[MarkerCalib][DIAG] Szene-Liste: {len(good_values)} IDs gespeichert.")
            else:
                print(f"[MarkerCalib][DIAG] Existiert im Referenzset (Name)? {example.name in good_values}")
                print(f"[MarkerCalib][DIAG] Szene-Liste: {len(good_values)} Namen gespeichert.")
            print(f"[MarkerCalib][DIAG] Beispiele: {good_values[:10]}")
        else:
            print("[MarkerCalib][DIAG] Keine aktiven Marker zur Analyse verfügbar.")

    print("[MarkerCalib] ---- Diagnose-Phase abgeschlossen ----\n")
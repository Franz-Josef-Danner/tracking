# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# UUID-basierte Version – kompatibel mit "good_tracks" / "best_tracks"
# Persistent über track["kt_uid"], keine volatilen Speicheradressen mehr
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple
import bpy, uuid


# ============================================================
# Low-level Marker Utilities
# ============================================================

def _ensure_uuid(track: bpy.types.MovieTrackingTrack) -> str:
    """Garantiert, dass jeder Track eine persistente UUID trägt."""
    if "kt_uid" not in track:
        track["kt_uid"] = str(uuid.uuid4())
    return track["kt_uid"]

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


# ============================================================
# Core Correction (UUID-basiert)
# ============================================================

def _select_good_set(scene):
    """Wählt das aktive Set aus der Szene und erkennt automatisch UUID- oder Namenlisten."""
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene

    if has_good and has_best:
        print("[MarkerCalib] ❌ Konflikt: Sowohl 'good_tracks' als auch 'best_tracks' vorhanden.")
        return None, None

    key = "good_tracks" if has_good else ("best_tracks" if has_best else None)
    if key is None:
        print("[MarkerCalib] ⚠️ Kein gültiges Referenzset vorhanden")
        return None, None

    raw = list(scene[key])
    # UUID-Erkennung: typische 36-stellige Zeichenkette mit Bindestrichen
    def _is_uuid(v: str) -> bool:
        return isinstance(v, str) and len(v) >= 30 and "-" in v

    is_uuid_based = all(_is_uuid(v) for v in raw)
    print(f"[MarkerCalib] ✅ Verwende '{key}'-Set "
          f"({len(raw)} Einträge, {'UUID' if is_uuid_based else 'Name'}-basiert)")
    return raw, is_uuid_based


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
    good_values, uuid_based = _select_good_set(scene)
    if not good_values:
        print("[MarkerCalib] ❌ Abbruch – kein valider Referenzsatz.")
        return

    # --- Referenzmenge vorbereiten ---
    all_tracks = list(clip.tracking.tracks)
    track_map_uuid = { _ensure_uuid(t): t for t in all_tracks }

    if uuid_based:
        good_tracks = [track_map_uuid[uid] for uid in good_values if uid in track_map_uuid]
        missing = [uid for uid in good_values if uid not in track_map_uuid]
    else:
        name_map = {t.name: t for t in all_tracks}
        good_tracks = [name_map[n] for n in good_values if n in name_map]
        missing = [n for n in good_values if n not in name_map]

    print(f"[MarkerCalib] Aufgelöste Tracks: {len(good_tracks)}  Fehlende: {len(missing)}")
    if missing:
        print(f"[MarkerCalib] Fehlende Beispiele: {missing[:5]}")

    # --- Vergleich zur aktuellen Auswahl ---
    sel_names = [t.name for t in selected_tracks]
    sel_uuids = [_ensure_uuid(t) for t in selected_tracks]

    if uuid_based:
        intersect = [uid for uid in sel_uuids if uid in good_values]
        diff = [uid for uid in sel_uuids if uid not in good_values]
    else:
        intersect = [n for n in sel_names if n in good_values]
        diff = [n for n in sel_names if n not in good_values]

    print(f"[MarkerCalib] Vergleich Selektierte vs Referenz:")
    print(f"   - Selektiert: {len(selected_tracks)}")
    print(f"   - Im Referenz-Set: {len(intersect)}")
    print(f"   - Nicht im Referenz-Set: {len(diff)}")
    if intersect:
        print(f"   - Beispiele im Schnitt: {intersect[:5]}")
    if diff:
        print(f"   - Beispiele außerhalb: {diff[:5]}")

    # --- Frameweise Analyse ---
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

        if uuid_based:
            in_good = [t for t in frame_tracks if t.get("kt_uid") in good_values]
        else:
            in_good = [t for t in frame_tracks if t.name in good_values]
        print(f"   → {len(in_good)} dieser Marker auch im Referenzset")

    # --- Zählen existierender Referenzmarker ---
    def _count_exist(tracks, f):
        return sum(1 for t in tracks if marker_exists(t, f))

    for lbl, f in zip(labels, frames):
        if f is None:
            continue
        cnt = _count_exist(good_tracks, f)
        print(f"[MarkerCalib] Existierende Referenzmarker @ {lbl}({f}): {cnt}")

    # --- Aktive Marker pro Frame sammeln ---
    fa_marker = get_active_markers(context, frame_a)
    fb_marker = get_active_markers(context, frame_b)
    fc_marker = get_active_markers(context, frame_c) if frame_c else []
    fd_marker = get_active_markers(context, frame_d) if frame_d else []

    # Objekt-Identität prüfen
    if fa_marker and good_tracks:
        overlap = sum(1 for m in fa_marker for g in good_tracks if m is g)
        print(f"[MarkerCalib] FrameA Objekt-Identität mit Referenz: {overlap}/{len(fa_marker)}")

    # --- Gute Marker je Frame ---
    if uuid_based:
        fa_good = [m for m in fa_marker if m.get("kt_uid") in good_values]
        fb_good = [m for m in fb_marker if m.get("kt_uid") in good_values]
        fc_good = [m for m in fc_marker if m.get("kt_uid") in good_values]
        fd_good = [m for m in fd_marker if m.get("kt_uid") in good_values]
    else:
        fa_good = [m for m in fa_marker if m.name in good_values]
        fb_good = [m for m in fb_marker if m.name in good_values]
        fc_good = [m for m in fc_marker if m.name in good_values]
        fd_good = [m for m in fd_marker if m.name in good_values]

    print(f"[MarkerCalib] Gute Marker je Frame:")
    print(f"   A={len(fa_good)}  B={len(fb_good)}  C={len(fc_good)}  D={len(fd_good)}")

    # --- Diagnose ---
    if sum(len(x) for x in (fa_good, fb_good, fc_good, fd_good)) == 0:
        print("[MarkerCalib][DIAG] Kein Frame mit Übereinstimmung gefunden!")
        if fa_marker:
            ex = fa_marker[0]
            print(f"[MarkerCalib][DIAG] Beispielmarker: {ex.name}, Typ={type(ex)}")
            uid = ex.get("kt_uid")
            if uuid_based:
                exists = uid in good_values
                print(f"[MarkerCalib][DIAG] Existiert im Referenzset (UUID)? {exists}")
                print(f"[MarkerCalib][DIAG] Szene-Liste: {len(good_values)} UUIDs gespeichert.")
            else:
                print(f"[MarkerCalib][DIAG] Existiert im Referenzset (Name)? {ex.name in good_values}")
                print(f"[MarkerCalib][DIAG] Szene-Liste: {len(good_values)} Namen gespeichert.")
            print(f"[MarkerCalib][DIAG] Beispiele: {good_values[:10]}")
        else:
            print("[MarkerCalib][DIAG] Keine aktiven Marker zur Analyse verfügbar.")

    print("[MarkerCalib] ---- Diagnose-Phase abgeschlossen ----\n")

# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# UUID-basierte Version – kompatibel mit "good_tracks" / "best_tracks"
# Persistenz über Scene-Strings: "good_tracks" (UUID-Liste) und
# "good_tracks_uuid_map" (als String gespeichertes Dict {uuid: name})
# KEINE IDProperties auf MovieTrackingTrack!
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple
import bpy, ast


# ============================================================
# Low-level Marker Utilities
# ============================================================

def _find_marker_at_frame(track, frame: int):
    try:
        mk = track.markers.find_frame(int(frame))
        return mk if mk and not mk.mute else None
    except Exception:
        return None

def marker_exists(track, frame: int) -> bool:
    return _find_marker_at_frame(track, frame) is not None

def get_marker_position(track, frame: int) -> Tuple[float, float]:
    mk = _find_marker_at_frame(track, frame)
    if mk:
        return float(mk.co[0]), float(mk.co[1])
    head = track.markers[0] if track.markers else None
    return (float(head.co[0]), float(head.co[1])) if head else (0.0, 0.0)

def set_marker_position(track, frame: int, x: float, y: float):
    mk = _find_marker_at_frame(track, frame)
    if mk:
        mk.co[0] = float(x)
        mk.co[1] = float(y)

def _active_clip(context):
    space = getattr(context, "space_data", None)
    return getattr(space, "clip", None) if space else None

def _iter_active_tracks_at_frame(context, frame: int):
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr

def get_active_markers(context, frame: Optional[int]):
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))


# ============================================================
# Core: Referenz-Set Auswahl & Mapping
# ============================================================

def _select_good_set(scene):
    """
    Wählt 'good_tracks' oder 'best_tracks'.
    Ermittelt, ob UUID-basiert (über Szenen-Strings) oder Namen-basiert.
    """
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene

    if has_good and has_best:
        print("[MarkerCalib] ❌ Konflikt: Sowohl 'good_tracks' als auch 'best_tracks' vorhanden.")
        return None, None, None

    key = "good_tracks" if has_good else ("best_tracks" if has_best else None)
    if key is None:
        print("[MarkerCalib] ⚠️ Kein gültiges Referenzset vorhanden")
        return None, None, None

    raw = list(scene[key])

    # UUID-Erkennung: typische Strings mit Bindestrichen, ~36 Zeichen
    def _is_uuid(v: str) -> bool:
        return isinstance(v, str) and "-" in v and len(v) >= 30

    is_uuid_based = all(_is_uuid(v) for v in raw)

    name_to_uuid = {}
    if is_uuid_based:
        # Versuche, die Mapping-Tabelle (UUID -> Name) zu lesen
        map_key = f"{key}_uuid_map"
        if map_key in scene:
            try:
                uuid_to_name = ast.literal_eval(scene[map_key])
                # Rückwärts-Mapping für schnellen Name->UUID Lookup
                name_to_uuid = {name: uid for uid, name in uuid_to_name.items()}
            except Exception as e:
                print(f"[MarkerCalib] ⚠️ UUID-Map konnte nicht gelesen werden: {e}")
        else:
            print(f"[MarkerCalib] ⚠️ Kein '{map_key}' im Scene-Storage – Fallback nur über Namen möglich.")

    print(f"[MarkerCalib] ✅ Verwende '{key}'-Set "
          f"({len(raw)} Einträge, {'UUID' if is_uuid_based else 'Name'}-basiert)")
    return raw, is_uuid_based, name_to_uuid


# ============================================================
# Korrekturlogik
# ============================================================

def _robust_average(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """
    Einfache robuste Mittelung:
    - entfernt Ausreißer über Median-Filter (1-Punkt-Trim, falls >=3 Punkte)
    - berechnet Mittelwert der verbleibenden Punkte
    """
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    # Trim nur, wenn genug Punkte
    if len(points) >= 3:
        sx = sorted(xs); sy = sorted(ys)
        sx = sx[1:-1]; sy = sy[1:-1]
        if not sx or not sy:
            sx, sy = xs, ys
    else:
        sx, sy = xs, ys
    avg_x = sum(sx) / len(sx)
    avg_y = sum(sy) / len(sy)
    return (avg_x, avg_y)


def _collect_prev_positions_for_track(track, frames: List[int]) -> List[Tuple[int, Tuple[float, float]]]:
    out = []
    for f in frames:
        if f is None:
            continue
        if marker_exists(track, f):
            out.append((f, get_marker_position(track, f)))
    return out


def correct_marker_positions(context, selected_tracks, frame_a, frame_b, frame_c=None, frame_d=None):
    """
    Korrigiert Marker-Positionen im Frame A anhand der gleichen Tracks in B/C/D.
    – Verwendet UUID-Referenzmenge ('good_tracks' + Map) falls vorhanden.
    – Loggt detailliert: verwendete Tracks, vorher/nachher, Delta.
    """
    print("\n[MarkerCalib] ---- Starte Marker-Korrektur ----")
    print(f"[MarkerCalib] Frames: A={frame_a}, B={frame_b}, C={frame_c}, D={frame_d}")
    print(f"[MarkerCalib] Selektierte Marker (input): {len(selected_tracks)}")

    scene = context.scene
    clip = _active_clip(context)
    if not clip:
        print("[MarkerCalib] ❌ Kein aktiver Clip – Abbruch.")
        return

    print(f"[MarkerCalib] Aktiver Clip: {clip.name}")
    good_values, uuid_based, name_to_uuid = _select_good_set(scene)
    if not good_values:
        print("[MarkerCalib] ❌ Abbruch – kein valider Referenzsatz.")
        return

    # Referenz-All-Set (für schnelles Membership)
    good_set = set(good_values)

    # Diagnose: Auswahl vs Referenz
    sel_names = [t.name for t in selected_tracks]
    if uuid_based and name_to_uuid:
        sel_uids = [name_to_uuid.get(n) for n in sel_names]
        intersect = [uid for uid in sel_uids if uid and uid in good_set]
        diff = [uid for uid in sel_uids if (uid is None) or (uid not in good_set)]
    else:
        # Fallback: Namen vergleichen
        intersect = [n for n in sel_names if n in good_set]
        diff = [n for n in sel_names if n not in good_set]

    print(f"[MarkerCalib] Vergleich Selektierte vs Referenz:")
    print(f"   - Selektiert: {len(selected_tracks)}")
    print(f"   - Im Referenz-Set: {len(intersect)}")
    print(f"   - Nicht im Referenz-Set: {len(diff)}")
    if intersect:
        print(f"   - Beispiele im Schnitt: {intersect[:5]}")
    if diff:
        print(f"   - Beispiele außerhalb: {diff[:5]}")

    # Aktive Marker in den Frames sammeln (für Übersicht)
    frames = [frame_a, frame_b, frame_c, frame_d]
    labels = ["A", "B", "C", "D"]
    for lbl, f in zip(labels, frames):
        if f is None:
            continue
        frame_tracks = get_active_markers(context, f)
        print(f"[MarkerCalib] Frame {lbl}({f}): {len(frame_tracks)} aktive Marker")
        if frame_tracks:
            print("   → Namen:", [t.name for t in frame_tracks][:10])
        in_good = []
        if uuid_based and name_to_uuid:
            in_good = [t for t in frame_tracks if (name_to_uuid.get(t.name) in good_set)]
        else:
            in_good = [t for t in frame_tracks if t.name in good_set]
        print(f"   → {len(in_good)} dieser Marker auch im Referenzset")

    # ===========================
    # KORREKTUR-PASS
    # ===========================
    used = 0
    corrected = 0
    skipped = 0

    prev_frames = [frame_b, frame_c, frame_d]  # B/C/D als Historie für Korrektur

    for tr in selected_tracks:
        tr_name = tr.name
        # prüfen, ob Track zum Referenz-Set gehört
        in_set = False
        if uuid_based and name_to_uuid:
            uid = name_to_uuid.get(tr_name)
            in_set = (uid in good_set) if uid else False
        else:
            in_set = (tr_name in good_set)

        if not in_set:
            print(f"[MarkerCalib][SKIP] '{tr_name}' nicht im Referenz-Set.")
            skipped += 1
            continue

        used += 1

        # Positionssammlung: B/C/D vorhandene Marker
        prev_pos = _collect_prev_positions_for_track(tr, prev_frames)
        have_a = marker_exists(tr, frame_a)

        print(f"[MarkerCalib][Track] {tr_name}: in_set={in_set}, "
              f"prev_markers={len(prev_pos)}, has_A={have_a}")

        if not have_a:
            print(f"[MarkerCalib][SKIP] '{tr_name}' hat im Frame A({frame_a}) keinen Marker.")
            skipped += 1
            continue

        if not prev_pos:
            print(f"[MarkerCalib][SKIP] '{tr_name}': keine verwertbaren Vorframes (B/C/D).")
            skipped += 1
            continue

        # Log Detailliste der Vorframes
        for f, pos in prev_pos:
            print(f"   · PrevPos @ {f}: ({pos[0]:.6f}, {pos[1]:.6f})")

        # Zielposition = robuste Mittelung der Vorframes
        tgt = _robust_average([p for _, p in prev_pos])
        if tgt is None:
            print(f"[MarkerCalib][SKIP] '{tr_name}': Robustmittelung fehlgeschlagen.")
            skipped += 1
            continue

        before = get_marker_position(tr, frame_a)
        dx = tgt[0] - before[0]
        dy = tgt[1] - before[1]

        # Nur loggen, wenn es eine sichtbare Abweichung gibt
        print(f"[MarkerCalib][APPLY] '{tr_name}': "
              f"A_before=({before[0]:.6f}, {before[1]:.6f}) → "
              f"A_target=({tgt[0]:.6f}, {tgt[1]:.6f})  Δ=({dx:.6f}, {dy:.6f})")

        # Anwenden
        set_marker_position(tr, frame_a, tgt[0], tgt[1])
        after = get_marker_position(tr, frame_a)

        print(f"[MarkerCalib][OK] '{tr_name}': A_after=({after[0]:.6f}, {after[1]:.6f})")
        corrected += 1

    # Zusammenfassung
    print(f"[MarkerCalib] ---- Korrektur-Zusammenfassung ----")
    print(f"[MarkerCalib]   Verwendet (im Set): {used}")
    print(f"[MarkerCalib]   Korrigiert:         {corrected}")
    print(f"[MarkerCalib]   Übersprungen:       {skipped}")
    print("[MarkerCalib] ---- Diagnose-Phase abgeschlossen ----\n")

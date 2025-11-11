# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# UUID-/Name-agnostische Nutzung von 'good_tracks'/'best_tracks' als
# reine Referenzbasis. Selektierte Marker werden IMMER korrigiert,
# auch wenn sie NICHT im Referenz-Set stehen.
# Persistenz der Zuordnung erfolgt über Scene-Strings:
#   - scene['good_tracks'] oder scene['best_tracks'] : Liste (UUIDs oder Namen)
#   - scene['..._uuid_map'] : "{uuid: name, ...}" (optional für UUID→Name)
#   - scene['..._names']    : [Namen] (optional)
# KEINE IDProperties auf MovieTrackingTrack!
# ---------------------------------------------------------------------

from typing import List, Tuple, Optional, Dict, Iterable
import bpy, ast, math

# ============================================================
# Low-level Marker Utilities
# ============================================================

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    clip_ui = getattr(space, "clip", None) if space else None
    clip_edit = getattr(context, "edit_movieclip", None)
    return clip_ui or clip_edit

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

def set_marker_position(track, frame: int, x: float, y: float) -> None:
    mk = _find_marker_at_frame(track, frame)
    if mk:
        mk.co[0] = float(x); mk.co[1] = float(y)

def _iter_active_tracks_at_frame(context, frame: int):
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr

def get_active_markers(context, frame: Optional[int]) -> List[bpy.types.MovieTrackingTrack]:
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))

# ============================================================
# Referenz-Set Auswahl & Mapping
# ============================================================

def _select_reference_names(scene) -> Tuple[Optional[List[str]], str]:
    """
    Liefert die NAMEN der Referenz-Tracks, unabhängig davon, ob Scene-Storage
    UUID-basiert ist. Versucht, *_uuid_map zu lesen und auf Namen zu mappen.
    Rückgabe: (names_or_none, chosen_key_str)
    """
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene

    if has_good and has_best:
        print("[MarkerCalib] ❌ Konflikt: Sowohl 'good_tracks' als auch 'best_tracks' vorhanden.")
        return None, ""

    key = "good_tracks" if has_good else ("best_tracks" if has_best else None)
    if key is None:
        print("[MarkerCalib] ⚠️ Kein gültiges Referenzset vorhanden.")
        return None, ""

    raw = list(scene[key])

    # Prüfe, ob wir direkt Namen haben
    # (falls store_tracks_in_scene zusätzlich <key>_names setzt)
    names_key = f"{key}_names"
    if names_key in scene:
        names = list(scene[names_key])
        print(f"[MarkerCalib] Referenz über '{names_key}' (Namen) – {len(names)} Einträge")
        return names, key

    # Sonst: UUID-Map lesen und daraus Namen gewinnen
    map_key = f"{key}_uuid_map"
    if map_key in scene:
        try:
            uuid_to_name = ast.literal_eval(scene[map_key])
            # Wenn raw UUIDs sind → mappe zu Namen; wenn raw bereits Namen → nutze direkt
            def looks_like_uuid(s: str) -> bool:
                return isinstance(s, str) and "-" in s and len(s) >= 30
            if all(looks_like_uuid(v) for v in raw):
                names = [uuid_to_name.get(v) for v in raw if uuid_to_name.get(v)]
                return names, key
            else:
                # raw scheinen Namen zu sein
                return raw, key
        except Exception as e:
            print(f"[MarkerCalib] ⚠️ UUID-Map konnte nicht gelesen werden: {e}")
            # Fallback: behandle raw als Namen
            return raw, key

    # Kein Map vorhanden → behandle raw als Namen
    return raw, key

# ============================================================
# Hilfsfunktionen für Berechnungen
# ============================================================

def _robust_mean(vecs: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Einfaches getrimmtes Mittel (1 Punkt) bei >=3, sonst Mittelwert."""
    if not vecs:
        return None
    if len(vecs) == 1:
        return vecs[0]
    xs = [v[0] for v in vecs]; ys = [v[1] for v in vecs]
    if len(vecs) >= 3:
        sx = sorted(xs)[1:-1]; sy = sorted(ys)[1:-1]
        if not sx or not sy:
            sx, sy = xs, ys
    else:
        sx, sy = xs, ys
    return (sum(sx)/len(sx), sum(sy)/len(sy))

def _radial_weight(p_ref: Tuple[float, float], p_q: Tuple[float, float], eps: float = 1e-4) -> float:
    dx = p_ref[0] - p_q[0]; dy = p_ref[1] - p_q[1]
    dist = math.sqrt(dx*dx + dy*dy)
    return 1.0 / (eps + dist)

def _collect_positions_by_name(clip: bpy.types.MovieClip, frame: int, names: Iterable[str]) -> Dict[str, Tuple[float,float]]:
    """Liefert {name: (x,y)} für alle referenzierten Namen, die im Frame Marker haben."""
    out: Dict[str, Tuple[float,float]] = {}
    name_map = {t.name: t for t in clip.tracking.tracks}
    for n in names:
        t = name_map.get(n)
        if not t: 
            continue
        if marker_exists(t, frame):
            out[n] = get_marker_position(t, frame)
    return out

# ============================================================
# Hauptlogik
# ============================================================

def correct_marker_positions(context, selected_tracks: List[bpy.types.MovieTrackingTrack],
                             frame_a: int, frame_b: int, frame_c: Optional[int]=None, frame_d: Optional[int]=None):
    """
    Korrigiert IMMER die selektierten Marker (Ziel), unabhängig davon,
    ob sie im Referenz-Set stehen. Das Referenz-Set definiert nur die
    'Good'-Nachbarschaft zur Bewegungsableitung.
    """
    print("\n[MarkerCalib] ---- Starte Marker-Korrektur ----")
    print(f"[MarkerCalib] Frames: A={frame_a}, B={frame_b}, C={frame_c}, D={frame_d}")
    print(f"[MarkerCalib] Selektierte Marker (input): {len(selected_tracks)}")

    scene = context.scene
    clip = _active_clip(context)
    if not clip or not getattr(clip, "tracking", None):
        print("[MarkerCalib] ❌ Kein aktiver Clip – Abbruch.")
        return

    print(f"[MarkerCalib] Aktiver Clip: {clip.name}")

    # Referenznamen besorgen (good/best)
    ref_names, key = _select_reference_names(scene)
    if not ref_names:
        print("[MarkerCalib] ❌ Abbruch – keine gültige Referenzbasis.")
        return

    ref_name_set = set(ref_names)
    print(f"[MarkerCalib] Referenz-Namensmenge ({len(ref_name_set)}): Beispiele → {list(ref_name_set)[:10]}")

    # Mindestbasis
    min_required = getattr(scene, "kaiserlich_markers_per_frame", 20) / 2.0
    print(f"[MarkerCalib] Mindestbasis (min_required): {min_required}")

    # Aktive Marker je Frame (nur zur Diagnose; Selektierte werden unabhängig davon korrigiert)
    frames = [frame_a, frame_b, frame_c, frame_d]
    labels = ["A", "B", "C", "D"]
    active_by_frame: Dict[int, List[bpy.types.MovieTrackingTrack]] = {}

    for lbl, f in zip(labels, frames):
        if f is None:
            continue
        fm = get_active_markers(context, f)
        active_by_frame[f] = fm
        names_here = [t.name for t in fm]
        in_ref = [n for n in names_here if n in ref_name_set]
        print(f"[MarkerCalib] Frame {lbl}({f}): {len(fm)} aktive Marker (Ref-Schnitt: {len(in_ref)})")
        if fm:
            print("   → Namen:", names_here[:10])

    # Moduswahl 4→3→2 basierend auf Ref-Schnitt im ältesten verfügbaren Frame
    def ref_count(f: Optional[int]) -> int:
        if f is None: 
            return 0
        return sum(1 for t in active_by_frame.get(f, []) if t.name in ref_name_set)

    cnt_a = ref_count(frame_a)
    cnt_b = ref_count(frame_b)
    cnt_c = ref_count(frame_c)
    cnt_d = ref_count(frame_d)

    mode = 0
    if frame_d is not None and cnt_d >= min_required and cnt_c >= 1 and cnt_b >= 1:
        mode = 4
    elif frame_c is not None and cnt_c >= min_required and cnt_b >= 1:
        mode = 3
    elif cnt_b >= min_required:
        mode = 2
    elif cnt_a >= min_required:
        # Nur A hat genug Good → keine Korrektur notwendig
        mode = 1
    else:
        mode = 0

    print(f"[MarkerCalib] Moduswahl: {mode}-Frame (Counts A/B/C/D = {cnt_a}/{cnt_b}/{cnt_c}/{cnt_d})")

    if mode == 0:
        print("[MarkerCalib] ❌ Zu wenige gültige Referenzen – Abbruch.")
        return
    if mode == 1:
        print("[MarkerCalib] ✅ Nur Frame A ausreichend – keine Korrektur erforderlich.")
        return

    # Referenzpositionen pro Frame (nur für Ref-Namen)
    posA = _collect_positions_by_name(clip, frame_a, ref_name_set)
    posB = _collect_positions_by_name(clip, frame_b, ref_name_set)
    posC = _collect_positions_by_name(clip, frame_c, ref_name_set) if (mode >= 3 and frame_c is not None) else {}
    posD = _collect_positions_by_name(clip, frame_d, ref_name_set) if (mode >= 4 and frame_d is not None) else {}

    # Bewegungsmodell (Ref-Geschwindigkeiten pro Name)
    ref_vel: Dict[str, Tuple[float,float]] = {}

    if mode == 2:
        # einfache Differenz B→A
        for n in list(set(posA.keys()) & set(posB.keys())):
            vx = posA[n][0] - posB[n][0]
            vy = posA[n][1] - posB[n][1]
            ref_vel[n] = (vx, vy)
    elif mode == 3:
        # mittlere Velocity aus B→A und C→B
        commonAB = list(set(posA.keys()) & set(posB.keys()))
        commonBC = list(set(posB.keys()) & set(posC.keys()))
        common = set(commonAB) & set(commonBC)
        for n in common:
            v1 = (posA[n][0]-posB[n][0], posA[n][1]-posB[n][1])
            v2 = (posB[n][0]-posC[n][0], posB[n][1]-posC[n][1])
            v = _robust_mean([v1, v2])
            if v:
                ref_vel[n] = v
    elif mode == 4:
        # mittlere Velocity aus A-B, B-C, C-D
        commonAB = set(posA.keys()) & set(posB.keys())
        commonBC = set(posB.keys()) & set(posC.keys())
        commonCD = set(posC.keys()) & set(posD.keys())
        common = list(commonAB & commonBC & commonCD)
        for n in common:
            vAB = (posA[n][0]-posB[n][0], posA[n][1]-posB[n][1])
            vBC = (posB[n][0]-posC[n][0], posB[n][1]-posC[n][1])
            vCD = (posC[n][0]-posD[n][0], posC[n][1]-posD[n][1])
            v = _robust_mean([vAB, vBC, vCD])
            if v:
                ref_vel[n] = v

    print(f"[MarkerCalib] Referenzvektoren: {len(ref_vel)} (Beispiele: {list(ref_vel.items())[:5]})")

    # Aggregation pro selektiertem Marker (unabhängig davon, ob im Set!)
    used = 0
    corrected = 0
    skipped = 0

    # Dämpfung adaptiv begrenzen
    base_damp = 0.05

    # Name→Track Map (für Referenz-Positionen)
    name_to_track = {t.name: t for t in clip.tracking.tracks}

    for sm in selected_tracks:
        name = sm.name
        hasA = marker_exists(sm, frame_a)
        hasB = marker_exists(sm, frame_b)

        if not hasA or not hasB:
            print(f"[MarkerCalib][SKIP] '{name}': fehlender Marker in A({hasA})/B({hasB}).")
            skipped += 1
            continue

        pA = get_marker_position(sm, frame_a)
        pB = get_marker_position(sm, frame_b)

        # Nachbarschaftsgewichtung gegen Ref-Nachbarn, die in A existieren
        vxw = 0.0; vyw = 0.0; wsum = 0.0
        ref_used = 0

        for rn, (vx, vy) in ref_vel.items():
            if rn not in posA:
                continue
            pRefA = posA[rn]
            w = _radial_weight(pA, pRefA, eps=1e-4)
            vxw += w * vx
            vyw += w * vy
            wsum += w
            ref_used += 1

        if wsum <= 0.0 or ref_used == 0:
            print(f"[MarkerCalib][SKIP] '{name}': keine verwertbaren Referenzen in A.")
            skipped += 1
            continue

        avg_v = (vxw/wsum, vyw/wsum)

        # Prognose aus B + avg_v
        pred = (pB[0] + avg_v[0], pB[1] + avg_v[1])

        # Gedämpftes Update (±5% Corridor relativ zur prognostizierten Delta)
        dx = pred[0] - pA[0]; dy = pred[1] - pA[1]
        damp = base_damp
        newA = (pA[0] + damp*dx, pA[1] + damp*dy)

        print(f"[MarkerCalib][APPLY] '{name}': "
              f"A_before=({pA[0]:.6f},{pA[1]:.6f})  "
              f"B=({pB[0]:.6f},{pB[1]:.6f})  "
              f"avg_v=({avg_v[0]:.6f},{avg_v[1]:.6f})  "
              f"pred=({pred[0]:.6f},{pred[1]:.6f})  "
              f"newA=({newA[0]:.6f},{newA[1]:.6f})  "
              f"ref_used={ref_used}")

        set_marker_position(sm, frame_a, newA[0], newA[1])
        corrected += 1
        used += 1

    print(f"[MarkerCalib] ---- Korrektur-Zusammenfassung ----")
    print(f"[MarkerCalib]   Modus:             {mode}-Frame")
    print(f"[MarkerCalib]   Selektiert:        {len(selected_tracks)}")
    print(f"[MarkerCalib]   Verwendete Targets:{used}")
    print(f"[MarkerCalib]   Korrigiert:        {corrected}")
    print(f"[MarkerCalib]   Übersprungen:      {skipped}")
    print("[MarkerCalib] ---- Diagnose-Phase abgeschlossen ----\n")

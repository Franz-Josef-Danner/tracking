# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Stabilisierung/Korrektur von Marker-Positionen im aktuellen Frame
# anhand stabiler Referenzen aus bis zu 4 Rückblick-Frames.
# Kompatibel mit:
#   - Szene-String "good_marker" ODER "best_marker" (mutual exclusive)
#   - Optionalen UUID-Maps: "<key>_uuid_map" als String-Dict {uuid: name}
#
# Log-Ausgaben:
#   [FRAME]   – Aktueller Frame der Korrektur
#   [TRACK]   – Aktueller Trackname
#   [FORMULA] – Einzelwerte (Gewicht, Distanz, Velocity)
#   [TRIM]    – Trimmed Mean (Samples, Ratio, Endmittel)
#   [RESULT]  – Alte vs neue Markerposition
#   [WARN]    – Abbruch oder unvollständige Referenzen
#   [SUMMARY] – Kompakte Statistik pro Aufruf
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple, Dict, Any
import bpy
import ast
import math


# ============================================================
# Logging-Helper (0=off, 1=summary, 2=normal, 3=verbose)
# ============================================================

def _dbg(scene: bpy.types.Scene, level: int, msg: str):
    lvl = int(getattr(scene, "kaiserlich_debug_level", 2) or 2)
    if lvl >= level:
        print(msg)


# ============================================================
# Low-level Marker Utilities
# ============================================================

def _find_marker_at_frame(track, frame: int):
    """Sicherer Zugriff auf Marker eines Tracks in einem Frame (muted ausgeschlossen)."""
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
    """Versucht den aktiven MovieClip aus dem aktuellen Context zu holen (CLIP_EDITOR bevorzugt)."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return space.clip

    wm = getattr(context, "window_manager", None)
    if not wm:
        return None
    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type == 'CLIP_EDITOR':
                sp = area.spaces.active
                if sp and getattr(sp, "clip", None):
                    return sp.clip
    return None


def _iter_active_tracks_at_frame(context, frame: int):
    """Liefert selektierte und im angegebenen Frame existierende Tracks des aktiven Clips."""
    clip = _active_clip(context)
    if not clip:
        return []
    for tr in clip.tracking.tracks:
        if tr.select and marker_exists(tr, frame):
            yield tr


def get_active_markers(context, frame: Optional[int]):
    """API-kompatibler Wrapper: aktive Tracks (selektiert & Marker existiert in frame)."""
    if frame is None:
        return []
    return list(_iter_active_tracks_at_frame(context, int(frame)))


# ============================================================
# Referenzmanagement (good_marker / best_marker)
# ============================================================

def _read_scene_string(scene: bpy.types.Scene, key: str) -> Optional[List[str]]:
    """Liest einen Szenen-String robust als Liste von Strings."""
    if key not in scene:
        return None
    raw = list(scene[key])
    out = []
    for v in raw:
        if isinstance(v, str):
            out.append(v)
        else:
            try:
                out.append(str(v))
            except Exception:
                pass
    return out


def _detect_uuid_mode(values: List[str]) -> bool:
    """Heuristik für UUID-Strings (Bindestrich + Länge ~36)."""
    if not values:
        return False
    def _is_uuid(s: str) -> bool:
        return isinstance(s, str) and "-" in s and len(s) >= 30
    return all(_is_uuid(v) for v in values)


def _load_uuid_map(scene: bpy.types.Scene, key: str) -> Dict[str, str]:
    """
    Liest optionale Map {uuid: name} aus Szene-String f"{key}_uuid_map".
    Gibt leeres Dict zurück, falls nicht vorhanden/lesbar.
    """
    map_key = f"{key}_uuid_map"
    if map_key not in scene:
        return {}
    try:
        data = ast.literal_eval(scene[map_key])
        if isinstance(data, dict):
            return {str(u): str(n) for u, n in data.items()}
    except Exception:
        pass
    return {}


def _select_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    """
    Mutual Exclusivity:
      - genau einer von "good_marker" oder "best_marker" muss existieren.
    """
    has_good = "good_marker" in scene
    has_best = "best_marker" in scene
    if has_good and has_best:
        print("[MarkerCorrection][WARN] Beide Referenz-Sets vorhanden – Konflikt.")
        return None
    if not has_good and not has_best:
        print("[MarkerCorrection][WARN] Kein Referenz-Set vorhanden.")
        return None
    return "good_marker" if has_good else "best_marker"


def _build_reference_name_set(context: bpy.types.Context,
                              scene: bpy.types.Scene) -> Optional[Dict[str, Any]]:
    """
    Liefert:
      {
        "key": "good_marker"|"best_marker",
        "is_uuid": bool,
        "ref_values": List[str],
        "uuid_to_name": Dict[str,str],
        "name_set": Set[str]
      }
    """
    key = _select_reference_key(scene)
    if key is None:
        return None

    ref_values = _read_scene_string(scene, key)
    if not ref_values:
        print(f"[MarkerCorrection][WARN] Szene-String {key} ist leer.")
        return None

    is_uuid = _detect_uuid_mode(ref_values)
    uuid_to_name = _load_uuid_map(scene, key) if is_uuid else {}

    clip = _active_clip(context)
    if not clip:
        name_set = set(uuid_to_name.values()) if is_uuid else set(ref_values)
    else:
        scene_names = {t.name for t in clip.tracking.tracks}
        if is_uuid and uuid_to_name:
            mapped_names = set(uuid_to_name.get(uid, "") for uid in ref_values)
            name_set = {n for n in mapped_names if n and n in scene_names}
        elif is_uuid and not uuid_to_name:
            name_set = set()
        else:
            name_set = {n for n in ref_values if n in scene_names}

    return {
        "key": key,
        "is_uuid": is_uuid,
        "ref_values": ref_values,
        "uuid_to_name": uuid_to_name,
        "name_set": name_set,
    }


# ============================================================
# Mathe / Robustheit
# ============================================================

def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def _radial_weight(p_target: Tuple[float, float],
                   p_ref: Tuple[float, float],
                   eps: float = 1e-6) -> float:
    """Gewicht = 1 / (eps + Distanz), Distanz = sqrt(dist2)."""
    d2 = _dist2(p_target, p_ref)
    w = 1.0 / (eps + math.sqrt(d2))
    # Formel-Log auf NORMAL-Level
    print(f"[MarkerCorrection][FORMULA] weight={w:.6f}  dist={math.sqrt(d2):.6f}")
    return w


def _trimmed_weighted_mean(vals: List[Tuple[float, float]],
                           weights: List[float],
                           trim_ratio: float = 0.10) -> Tuple[float, float]:
    """
    Trimmed Weighted Mean der Geschwindigkeitskomponenten.
    Bei <5 Samples → klassisches gewichtetes Mittel ohne Trimming.
    """
    n = len(vals)
    if n == 0:
        return 0.0, 0.0
    if n < 5:
        wsum = sum(weights) if weights else 0.0
        if wsum <= 0.0:
            return 0.0, 0.0
        vx = sum(v[0] * w for v, w in zip(vals, weights)) / wsum
        vy = sum(v[1] * w for v, w in zip(vals, weights)) / wsum
        print(f"[MarkerCorrection][TRIM] direct_mean  n={n}  vx={vx:.6f}  vy={vy:.6f}")
        return vx, vy

    # Sortiere nach Betrag des Velocity-Vektors und trimme Extremwerte
    combined = sorted(zip(vals, weights), key=lambda x: (x[0][0]**2 + x[0][1]**2))
    k = max(1, int(n * trim_ratio))
    trimmed = combined[k:-k] if n > 2 * k else combined
    vals_t, w_t = zip(*trimmed)
    wsum = sum(w_t)
    if wsum <= 0.0:
        return 0.0, 0.0
    vx = sum(v[0] * w for v, w in zip(vals_t, w_t)) / wsum
    vy = sum(v[1] * w for v, w in zip(vals_t, w_t)) / wsum
    print(f"[MarkerCorrection][TRIM] n={n} trim={trim_ratio*100:.1f}%  → vx={vx:.6f} vy={vy:.6f}")
    return vx, vy


# ============================================================
# Hauptfunktion
# ============================================================

def correct_marker_positions(scene: bpy.types.Scene,
                             good_markers,
                             selected_markers,
                             frame_a: Optional[int],
                             frame_b: Optional[int],
                             frame_c: Optional[int] = None,
                             frame_d: Optional[int] = None):
    """
    Korrigiert instabile Markerpositionen anhand stabiler Referenzen
    aus bis zu 4 vorherigen Frames.
    """

    # ---- Hard Guard: Ziel-Frame muss gesetzt sein -------------------
    if frame_b is None:
        _dbg(scene, 2, "[MarkerCorrection][WARN] frame_b ist None – Abbruch.")
        return

    ctx = bpy.context
    _dbg(scene, 2, f"[MarkerCorrection][FRAME] {int(frame_b)}")

    ref_info = _build_reference_name_set(ctx, scene)
    if not ref_info:
        _dbg(scene, 2, "[MarkerCorrection][WARN] Keine Referenzen gefunden – Abbruch.")
        return

    clip = _active_clip(ctx)
    if not clip:
        _dbg(scene, 2, "[MarkerCorrection][WARN] Kein aktiver Clip – Abbruch.")
        return

    # Vorbereitung
    all_tracks = {t.name: t for t in clip.tracking.tracks}

    # Stats für Summary
    stats_total = 0
    stats_moved = 0
    stats_skipped_no_target = 0
    stats_no_prev = 0

    def _same_pos(a, b, tol=1e-7):
        return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol

    for tr in selected_markers:
        if tr.name not in all_tracks:
            continue

        stats_total += 1

        if not marker_exists(tr, frame_b):
            stats_skipped_no_target += 1
            _dbg(scene, 3, f"[MarkerCorrection][TRACK] {tr.name}  skip: kein Marker im Ziel-Frame")
            continue

        p_cur = get_marker_position(tr, frame_b)
        velocities: List[Tuple[float, float]] = []
        weights: List[float] = []

        # Nur valide Rückblick-Frames berücksichtigen (eindeutig & sortiert)
        prev_frames = [f for f in {frame_a, frame_c, frame_d} if isinstance(f, int)]
        prev_frames.sort()

        for f_prev in prev_frames:
            if not marker_exists(tr, f_prev):
                continue
            p_prev = get_marker_position(tr, f_prev)
            vx = p_cur[0] - p_prev[0]
            vy = p_cur[1] - p_prev[1]
            w = _radial_weight(p_cur, p_prev)  # loggt FORMULA
            velocities.append((vx, vy))
            weights.append(w)
            _dbg(scene, 3, f"[MarkerCorrection][TRACK] {tr.name}  prev={f_prev}  v=({vx:+.6f},{vy:+.6f})  w={w:.6f}")

        if not velocities:
            stats_no_prev += 1
            _dbg(scene, 2, f"[MarkerCorrection][WARN] {tr.name}: keine gültigen Rückblick-Frames.")
            continue

        vx, vy = _trimmed_weighted_mean(velocities, weights)  # loggt TRIM
        new_pos = (p_cur[0] - vx, p_cur[1] - vy)

        if _same_pos(p_cur, new_pos):
            _dbg(scene, 3, f"[MarkerCorrection][RESULT] {tr.name}  unchanged  at=({p_cur[0]:.6f},{p_cur[1]:.6f})")
            continue

        set_marker_position(tr, frame_b, new_pos[0], new_pos[1])
        stats_moved += 1
        _dbg(scene, 2, f"[MarkerCorrection][TRACK] {tr.name}")
        _dbg(scene, 2, f"[MarkerCorrection][RESULT] old=({p_cur[0]:.6f},{p_cur[1]:.6f}) → new=({new_pos[0]:.6f},{new_pos[1]:.6f})")

    _dbg(scene, 1, f"[MarkerCorrection][SUMMARY] frame={int(frame_b)}  "
                   f"tracks={stats_total}  moved={stats_moved}  "
                   f"skipped_no_target={stats_skipped_no_target}  no_prev={stats_no_prev}")

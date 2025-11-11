# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Stabilisierung/Korrektur von Marker-Positionen im aktuellen Frame
# anhand stabiler Referenzen aus bis zu 4 Rückblick-Frames.
# Kompatibel mit:
#   - Szene-String "good_marker" ODER "best_marker" (mutual exclusive)
#   - Optionalen UUID-Maps: "<key>_uuid_map" als String-Dict {uuid: name}
#
# Funktionsnamen bleiben unverändert, damit bestehende Operatoren weiter
# funktionieren:
#   - _find_marker_at_frame
#   - marker_exists
#   - get_marker_position
#   - set_marker_position
#   - _active_clip
#   - _iter_active_tracks_at_frame
#   - get_active_markers
#   - correct_marker_positions
#
# Hinweise:
# - Keine IDProperties auf MovieTrackingTrack notwendig.
# - Robust-Logik: radiale Gewichtung + Trimmed Weighted Mean + Clamp.
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple, Dict, Any
import bpy
import ast
import math


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

    # Fallback: durch Areas gehen
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
# Intern: Referenzset-Auswahl (good_marker vs best_marker)
# ============================================================

def _read_scene_string(scene: bpy.types.Scene, key: str) -> Optional[List[str]]:
    """Liest einen Szenen-String (CollectionProperty-ähnlich oder IDProp-Liste) robust als Liste von Strings."""
    if key not in scene:
        return None
    raw = list(scene[key])
    # Normalisieren auf Strings
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
        # Erwartete Struktur: {uuid: name}
        if isinstance(data, dict):
            # Nur Strings übernehmen
            return {str(u): str(n) for u, n in data.items()}
    except Exception:
        pass
    return {}


def _select_reference_key(scene: bpy.types.Scene) -> Optional[str]:
    """
    Erzwingt Mutual Exclusivity:
      - genau einer von "good_marker" oder "best_marker" muss existieren.
    """
    has_good = "good_marker" in scene
    has_best = "best_marker" in scene
    if has_good and has_best:
        # Konsistenzfehler → Abbruch
        return None
    if not has_good and not has_best:
        # Keine Referenzbasis → Abbruch
        return None
    return "good_marker" if has_good else "best_marker"


def _build_reference_name_set(context: bpy.types.Context,
                              scene: bpy.types.Scene) -> Optional[Dict[str, Any]]:
    """
    Liefert ein Dict mit:
      {
        "key": "good_marker"|"best_marker",
        "is_uuid": bool,
        "ref_values": List[str],     # direkte Werte aus Szene-String (UUIDs ODER Namen)
        "uuid_to_name": Dict[str,str], # nur bei UUID-Modus
        "name_set": Set[str]         # effektive Namen zur Szeneabgleich/Selektion
      }
    """
    key = _select_reference_key(scene)
    if key is None:
        return None

    ref_values = _read_scene_string(scene, key)
    if not ref_values:
        return None

    is_uuid = _detect_uuid_mode(ref_values)
    uuid_to_name = _load_uuid_map(scene, key) if is_uuid else {}

    # Effektive Namensmenge bestimmen:
    clip = _active_clip(context)
    if not clip:
        # Ohne Clip können wir keine Namen verifizieren – wir nutzen nur das, was wir haben.
        name_set = set(uuid_to_name.values()) if is_uuid else set(ref_values)
    else:
        scene_names = {t.name for t in clip.tracking.tracks}
        if is_uuid and uuid_to_name:
            mapped_names = set(uuid_to_name.get(uid, "") for uid in ref_values)
            name_set = {n for n in mapped_names if n and n in scene_names}
        elif is_uuid and not uuid_to_name:
            # UUIDs vorhanden, aber keine Map → Fallback auf Namensmodus (defensiv)
            name_set = set()  # ohne Map keine sichere Zuordnung
        else:
            # Name-Modus
            name_set = {n for n in ref_values if n in scene_names}

    return {
        "key": key,
        "is_uuid": is_uuid,
        "ref_values": ref_values,
        "uuid_to_name": uuid_to_name,
        "name_set": name_set,
    }


# ============================================================
# Mathe/Robustheit: Velocity, Gewichtung, Aggregation
# ============================================================

def _dist2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx*dx + dy*dy


def _radial_weight(p_target: Tuple[float, float],
                   p_ref: Tuple[float, float],
                   eps: float = 1e-6) -> float:
    """Gewicht = 1 / (eps + Distanz), Distanz = sqrt(dist2)."""
    d2 = _dist2(p_target, p_ref)
    return 1.0 / (eps + math.sqrt(d2))


def _trimmed_weighted_mean(vals: List[Tuple[float, float]],  # [(vx, vy)]
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
        return vx, vy

    # Für x und y getrennt sortieren und trimmen
    idxs = list(range(n))

    # X-Komponente
    idxs_x = sorted(idxs, key=lambda i: vals[i][0])
    k = int(max(1, round(trim_ratio * n)))
    keep_x = idxs_x[k: n - k] if n - 2*k > 0 else idxs_x
    wsum_x = sum(weights[i] for i in keep_x)
    vx = sum(vals[i][0] * weights[i] for i in keep_x) / wsum_x if wsum_x > 0 else 0.0

    # Y-Komponente
    idxs_y = sorted(idxs, key=lambda i: vals[i][1])
    keep_y = idxs_y[k: n - k] if n - 2*k > 0 else idxs_y
    wsum_y = sum(weights[i] for i in keep_y)
    vy = sum(vals[i][1] * weights[i] for i in keep_y) / wsum_y if wsum_y > 0 else 0.0

    return vx, vy


def _predict_and_clamp(current_a: Tuple[float, float],
                       prev_b: Tuple[float, float],
                       v_avg: Tuple[float, float],
                       clamp_ratio: float = 0.05) -> Tuple[float, float]:
    """
    Prediction aus Vorframe (b) + mittlere Velocity → pred.
    Kalibrierung: Mittel zwischen aktueller Position (a) und pred.
    Clamp in [pred*(1-CR), pred*(1+CR)] komponentenweise.
    """
    pred_x = prev_b[0] + v_avg[0]
    pred_y = prev_b[1] + v_avg[1]

    calib_x = 0.5 * (current_a[0] + pred_x)
    calib_y = 0.5 * (current_a[1] + pred_y)

    # komponentenweises Clamp relativ zu pred
    def _clamp(v: float, p: float, r: float) -> float:
        lo = p * (1.0 - r)
        hi = p * (1.0 + r)
        return min(max(v, lo), hi)

    fx = _clamp(calib_x, pred_x, clamp_ratio)
    fy = _clamp(calib_y, pred_y, clamp_ratio)
    return fx, fy


# ============================================================
# Kernfunktion: Korrektur (Signaturen beibehalten)
# ============================================================

def correct_marker_positions(context,
                             selected_tracks: List[bpy.types.MovieTrackingTrack],
                             frame_a: int,
                             frame_b: int,
                             frame_c: Optional[int] = None,
                             frame_d: Optional[int] = None,
                             *,
                             trim_ratio: float = 0.10,
                             clamp_ratio: float = 0.05) -> None:
    """
    Korrigiert Markerpositionen im Frame A anhand stabiler ("good"/"best") Marker
    in den Rückblick-Frames B..D. Radial gewichtete Velocity-Aggregation
    (Trimmed Weighted Mean) + sanfter Clamp.
    """

    scene = context.scene
    clip = _active_clip(context)
    if not clip:
        # Kein aktiver Clip → Abbruch ohne Seiteneffekt
        return

    # Mutual Exclusivity + Referenzset herstellen
    ref_info = _build_reference_name_set(context, scene)
    if ref_info is None:
        # Beide oder keiner der Szene-Strings vorhanden → Abbruch
        return

    name_set = ref_info["name_set"]
    if not name_set:
        # Keine effektiven Referenznamen im Clip → Abbruch
        return

    # Mindestanzahl stabiler Marker (Gate)
    min_required_src = max(1, int(getattr(scene, "kaiserlich_markers_per_frame", 20) / 2))

    # Aktive Marker pro Frame schneiden mit Referenzset
    def _active_good(frame: Optional[int]) -> List[bpy.types.MovieTrackingTrack]:
        if frame is None:
            return []
        tracks = get_active_markers(context, frame)
        return [t for t in tracks if t.name in name_set]

    fa_good = _active_good(frame_a)
    fb_good = _active_good(frame_b)
    fc_good = _active_good(frame_c) if frame_c is not None else []
    fd_good = _active_good(frame_d) if frame_d is not None else []

    # Fallauswahl 4→3→2→0
    source_tracks = []
    mode = 0
    if frame_d is not None and len(fd_good) >= min_required_src:
        source_tracks = fd_good
        mode = 4
    elif frame_c is not None and len(fc_good) >= min_required_src:
        source_tracks = fc_good
        mode = 3
    elif len(fb_good) >= min_required_src:
        source_tracks = fb_good
        mode = 2
    else:
        # Falls im Ziel-Frame selbst genügend stabile Marker aktiv sind → keine Korrektur nötig
        if len(fa_good) >= min_required_src:
            return
        # sonst keine verlässliche Basis → Abbruch
        return

    # Hilfsfunktion zur Velocity-Schätzung je Referenz-Track
    def _estimate_velocity(ref_track) -> Optional[Tuple[float, float]]:
        # Positionsgriffe je nach Modus
        # Wir nutzen vorhandene Marker-Existenzprüfungen; fehlen Daten → None.
        try:
            if mode >= 2:
                if not (marker_exists(ref_track, frame_a) and marker_exists(ref_track, frame_b)):
                    return None
                a_pos = get_marker_position(ref_track, frame_a)
                b_pos = get_marker_position(ref_track, frame_b)
            if mode >= 3:
                if not marker_exists(ref_track, frame_c):
                    return None
                c_pos = get_marker_position(ref_track, frame_c)
            if mode >= 4:
                if not marker_exists(ref_track, frame_d):
                    return None
                d_pos = get_marker_position(ref_track, frame_d)

            if mode == 2:
                # v = (a - b)
                return (a_pos[0] - b_pos[0], a_pos[1] - b_pos[1])

            if mode == 3:
                # symmetrisch über a,b,c: 0.5 * ((b - c) + (a - b))
                vx = 0.5 * ((b_pos[0] - c_pos[0]) + (a_pos[0] - b_pos[0]))
                vy = 0.5 * ((b_pos[1] - c_pos[1]) + (a_pos[1] - b_pos[1]))
                return vx, vy

            if mode == 4:
                # ebenfalls mit a,b,c; d dient nur für Quellenauswahl (Abdeckung)
                vx = 0.5 * ((b_pos[0] - c_pos[0]) + (a_pos[0] - b_pos[0]))
                vy = 0.5 * ((b_pos[1] - c_pos[1]) + (a_pos[1] - b_pos[1]))
                return vx, vy
        except Exception:
            return None
        return None

    # Hauptschleife über selektierte Marker (sm)
    for sm in selected_tracks:
        # sm muss in den Frames a/b existieren, sonst keine Vorhersage möglich
        if not marker_exists(sm, frame_a) or not marker_exists(sm, frame_b):
            continue

        sm_a = get_marker_position(sm, frame_a)
        sm_b = get_marker_position(sm, frame_b)

        # Sammle Velocity-Samples von stabilen Referenzen + radiale Gewichte
        v_samples: List[Tuple[float, float]] = []
        w_samples: List[float] = []
        for gm in source_tracks:
            v = _estimate_velocity(gm)
            if v is None:
                continue
            # Gewicht anhand Abstand im Ziel-Frame A
            if not marker_exists(gm, frame_a):
                continue
            gm_a = get_marker_position(gm, frame_a)
            w = _radial_weight(sm_a, gm_a)
            v_samples.append(v)
            w_samples.append(w)

        if not v_samples:
            # Keine verlässlichen Referenzen → kein Eingriff
            continue

        v_avg = _trimmed_weighted_mean(v_samples, w_samples, trim_ratio=trim_ratio)
        final_xy = _predict_and_clamp(sm_a, sm_b, v_avg, clamp_ratio=clamp_ratio)
        set_marker_position(sm, frame_a, final_xy[0], final_xy[1])

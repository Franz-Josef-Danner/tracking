# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# UUID-basierte Version – kompatibel mit "good_tracks" / "best_tracks"
# Persistenz über Scene-Strings: "good_tracks" (UUID-Liste) und
# "good_tracks_uuid_map" (als String gespeichertes Dict {uuid: name})
# KEINE IDProperties auf MovieTrackingTrack!
# ---------------------------------------------------------------------

from typing import Iterable, List, Optional, Tuple
import bpy, ast

from ..Helper.snapshot import store_tracks_in_scene


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
    Gibt zusätzlich Log-Ausgabe über Abgleich mit Szenen-Tracks.
    """
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene

    if has_good and has_best:
        print("[MarkerCalibration] ❌ Konflikt: Sowohl 'good_tracks' als auch 'best_tracks' vorhanden.")
        return None, None, None

    key = "good_tracks" if has_good else ("best_tracks" if has_best else None)
    if key is None:
        print("[MarkerCalibration] ⚠️ Kein Track-String ('good_tracks' / 'best_tracks') vorhanden.")
        return None, None, None

    raw = list(scene[key])
    print(f"[MarkerCalibration] 🔍 Aktiver Key: {key} | Anzahl: {len(raw)}")

    # UUID-Erkennung: typische Strings mit Bindestrichen, ~36 Zeichen
    def _is_uuid(v: str) -> bool:
        return isinstance(v, str) and "-" in v and len(v) >= 30

    is_uuid_based = all(_is_uuid(v) for v in raw)

    name_to_uuid = {}
    if is_uuid_based:
        map_key = f"{key}_uuid_map"
        if map_key in scene:
            try:
                uuid_to_name = ast.literal_eval(scene[map_key])
                name_to_uuid = {name: uid for uid, name in uuid_to_name.items()}
            except Exception as e:
                print(f"[MarkerCalibration] ⚠️ UUID-Map fehlerhaft oder nicht lesbar: {e}")

    # --------------------------------------------------------
    # Vergleich mit Tracks in der Szene
    # --------------------------------------------------------
    clip = bpy.context.space_data.clip if bpy.context.space_data else None
    if clip:
        scene_tracks = [t.name for t in clip.tracking.tracks]
        print(f"[MarkerCalibration] 🎞️ Szene enthält {len(scene_tracks)} Tracks.")

        if is_uuid_based and name_to_uuid:
            mapped_names = list(name_to_uuid.keys())
            print(f"[MarkerCalibration] 🧩 UUID-basiert. Mapping-Einträge: {len(mapped_names)}")
            missing_in_scene = [n for n in mapped_names if n not in scene_tracks]
            extra_in_scene = [n for n in scene_tracks if n not in mapped_names]
            matched = [n for n in mapped_names if n in scene_tracks]
        else:
            mapped_names = raw
            print(f"[MarkerCalibration] 🔠 Name-basiert. Vergleich direkt nach Namen.")
            missing_in_scene = [n for n in mapped_names if n not in scene_tracks]
            extra_in_scene = [n for n in scene_tracks if n not in mapped_names]
            matched = [n for n in mapped_names if n in scene_tracks]

        print(f"[MarkerCalibration] ✅ Übereinstimmungen: {len(matched)}")
        print(f"[MarkerCalibration] ❌ Fehlend in Szene: {len(missing_in_scene)} → {missing_in_scene}")
        print(f"[MarkerCalibration] ⚠️ Extra in Szene (nicht im String): {len(extra_in_scene)} → {extra_in_scene}")
    else:
        print("[MarkerCalibration] ⚠️ Kein aktiver Clip zum Vergleich gefunden.")

    return raw, is_uuid_based, name_to_uuid


# ============================================================
# Korrekturlogik
# ============================================================

def _robust_average(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """Einfache robuste Mittelung mit Trimming und Mittelwert."""
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if len(points) >= 3:
        sx = sorted(xs)[1:-1]
        sy = sorted(ys)[1:-1]
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
    Führt zusätzlich Log-Vergleich zwischen Szenen-Tracks und gespeicherten Strings aus.
    """
    scene = context.scene
    clip = _active_clip(context)
    if not clip:
        print("[MarkerCalibration] ❌ Kein aktiver Clip – Abbruch.")
        return

    good_values, uuid_based, name_to_uuid = _select_good_set(scene)
    if not good_values:
        print("[MarkerCalibration] ⚠️ Kein gültiges Track-Set gefunden.")
        return

    good_set = set(good_values)
    prev_frames = [frame_b, frame_c, frame_d]

    print(f"[MarkerCalibration] ▶️ Starte Korrektur auf {len(selected_tracks)} selektierten Tracks...")

    for tr in selected_tracks:
        tr_name = tr.name
        if uuid_based and name_to_uuid:
            uid = name_to_uuid.get(tr_name)
            in_set = (uid in good_set) if uid else False
        else:
            in_set = (tr_name in good_set)

        if not in_set:
            print(f"   [Skip] {tr_name} – nicht in {('UUID' if uuid_based else 'Name')}-Set enthalten.")
            continue

        prev_pos = _collect_prev_positions_for_track(tr, prev_frames)
        have_a = marker_exists(tr, frame_a)
        if not have_a or not prev_pos:
            print(f"   [Skip] {tr_name} – keine Markerposition in Ziel- oder Vorframes.")
            continue

        tgt = _robust_average([p for _, p in prev_pos])
        if tgt is None:
            print(f"   [Skip] {tr_name} – keine gültigen Positionsdaten.")
            continue

        set_marker_position(tr, frame_a, tgt[0], tgt[1])
        print(f"   [OK] {tr_name} – korrigiert auf {tgt}")

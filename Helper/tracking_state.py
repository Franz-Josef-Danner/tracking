# Helper/tracking_state.py
# PEP 8-konform, deutsch kommentiert.

from __future__ import annotations

import bpy
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Callable, Optional

# Mapping "Anzahl" -> Motion Model (A1..A5)
MOTION_MODEL_BY_COUNT = {
    1: "Loc",
    2: "LocRot",
    3: "LocRotScale",
    4: "Perspective",
    5: "Affine",
}

SCENE_STATE_PROP = "tracking_state_json"  # JSON in der Szene
# Kern-Logik:
# - MAX_STEPS = 25  (5 Basis + 4 Triplet-Blöcke à 5 Schritte)
# - EXTENSION_STEPS = 10 (Zusatzläufe mit höchster Einstellung nach der letzten Stufe)
# - Abbruch erst nach MAX_STEPS + EXTENSION_STEPS + 1
MAX_STEPS = 25
EXTENSION_STEPS = 10
ABORT_AT = MAX_STEPS + EXTENSION_STEPS + 1  # = 25 + 10 + 1 → Abbruch beim 36. Besuch

@dataclass
class FrameEntry:
    # Kernwert für Ableitungen (Motion Model / Triplet)
    count: int = 1
    # Alt-Flags bleiben für Abwärtskompatibilität erhalten, werden aber nicht mehr genutzt
    anchor: bool = False
    interpolated: bool = False
    # A-Log (unverändert)
    A1: float = 0.0
    A2: float = 0.0
    A3: float = 0.0
    A4: float = 0.0
    A5: float = 0.0
    A6: float = 0.0
    A7: float = 0.0
    A8: float = 0.0
    A9: float = 0.0


# ---------- State laden/speichern ----------

def _get_state(context: bpy.types.Context) -> Dict[str, Any]:
    scene = context.scene
    raw = scene.get(SCENE_STATE_PROP, "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    state = {"frames": {}}  # key: str(frame) -> FrameEntry as dict
    _save_state(context, state)
    return state


# ---------- Reset API ----------

def reset_tracking_state(context: bpy.types.Context) -> None:
    """Setzt den gesamten Tracking-State (frames, counts, A-Werte) zurück."""
    try:
        state = {"frames": {}}
        _save_state(context, state)
        if "_tracking_triplet_mode" in context.scene:
            try:
                del context.scene["_tracking_triplet_mode"]
            except Exception:
                pass
    except Exception as exc:
        print(f"[tracking_state] Reset fehlgeschlagen: {exc}")
    return state


def _save_state(context: bpy.types.Context, state: Dict[str, Any]) -> None:
    context.scene[SCENE_STATE_PROP] = json.dumps(state, separators=(",", ":"))


def _ensure_frame_entry(state: Dict[str, Any], frame: int) -> Tuple[Dict[str, Any], bool]:
    frames = state.setdefault("frames", {})
    key = str(frame)
    if key not in frames:
        frames[key] = asdict(FrameEntry())
        return frames[key], True
    return frames[key], False


# ---------- Motion-Model / Triplet (erweiterte 25-Schritt-Logik) ----------

def _apply_model_triplet_for_count(context: bpy.types.Context, entry: Dict[str, Any]) -> None:
    """
    Setzt Motion-Model und Triplet-Flag ausgehend von entry['count'].
    Schritte:
      1..5    → Modelle 1..5, Triplet=None
      6..10   → Triplet=1, Modelle 1..5
      11..15  → Triplet=2, Modelle 1..5
      16..20  → Triplet=3, Modelle 1..5
      21..25  → Triplet=4, Modelle 1..5
      26..35  → (Verlängerung) Triplet=4, Modell=5 (höchste Einstellung) weiterführen
      36      → Abbruch (Triplet-Flag löschen)
    """
    count = int(entry.get("count", 1))
    if count >= ABORT_AT:
        _set_triplet_mode_on_scene(context, None)
        return
    # Basisphase: 1..5 (kein Triplet)
    if 1 <= count <= 5:
        model = MOTION_MODEL_BY_COUNT.get(count, "Loc")
        _set_motion_model_for_all_selected_tracks(context, model)
        _set_triplet_mode_on_scene(context, None)
        return
    # Triplet-Phasen: Blöcke à 5 Schritte
    # Blockindex 0..3 → Triplet 1..4 / innerhalb Block Schritt 1..5 → Modelle 1..5
    phase = count - 6  # 0-basiert ab Schritt 6
    block_idx = phase // 5  # 0..3
    step_in_block = (phase % 5) + 1  # 1..5
    trip_idx = min(4, block_idx + 1)
    model = MOTION_MODEL_BY_COUNT.get(step_in_block, "Loc")
    _set_motion_model_for_all_selected_tracks(context, model)
    _set_triplet_mode_on_scene(context, trip_idx)
    return

    # (Dead code guard – Logik endet vorher über return)

    # Verlängerungsfenster nach der letzten Stufe:
    # 26..(MAX_STEPS+EXTENSION_STEPS) → Triplet=4, Modell=Affine (A5)
    # (Wird effektiv nicht erreicht, da oben returnt; belassen als Doku)

def _set_motion_model_for_all_selected_tracks(context: bpy.types.Context, model: str) -> None:
    """Setzt Motion-Model für alle ausgewählten Tracks; Fallback auf Default, wenn keine Auswahl."""
    clip = context.edit_movieclip
    if not clip:
        return

    any_selected = False
    for obj in clip.tracking.objects:
        for track in obj.tracks:
            if getattr(track, "select", False):
                any_selected = True
                track.motion_model = model
    if not any_selected:
        clip.tracking.settings.default_motion_model = model


def _pick_best_model_from_A1_A5(entry: Dict[str, Any]) -> str:
    """Bestes Model = höchste A1..A5."""
    best_key = max(("A1", "A2", "A3", "A4", "A5"), key=lambda k: float(entry.get(k, 0.0)))
    idx = int(best_key[1])  # "A3" -> 3
    return MOTION_MODEL_BY_COUNT.get(idx, "Loc")


def _set_triplet_mode_on_scene(context: bpy.types.Context, triplet_index: Optional[int]) -> None:
    """Nur vorbereitend (Triplet-Handling baust du später drumherum)."""
    context.scene["_tracking_triplet_mode"] = int(triplet_index or 0)


# ---------- Reporting ----------

def _popup_error_report(context: bpy.types.Context, frame: int, entry: Dict[str, Any]) -> None:
    """Zeigt einen Error-Report als Popup mit allen A-Werten und count."""
    wm = context.window_manager
    title = f"Tracking-Report (ERROR) – Frame {frame} | Durchläufe: {entry.get('count', 0)}"

    # Inhalt aufbereiten
    lines = [
        f"A1: {entry.get('A1', 0):g}",
        f"A2: {entry.get('A2', 0):g}",
        f"A3: {entry.get('A3', 0):g}",
        f"A4: {entry.get('A4', 0):g}",
        f"A5: {entry.get('A5', 0):g}",
        f"A6: {entry.get('A6', 0):g}",
        f"A7: {entry.get('A7', 0):g}",
        f"A8: {entry.get('A8', 0):g}",
        f"A9: {entry.get('A9', 0):g}",
    ]
    best_model = _pick_best_model_from_A1_A5(entry)
    lines.append(f"Bestes Model (A1..A5): {best_model}")

    def draw(self, _context):
        col = self.layout.column(align=False)
        for ln in lines:
            col.label(text=ln, icon='ERROR')

    try:
        wm.popup_menu(draw, title=title, icon='ERROR')
    except Exception:
        # Fallback: Konsole
        print(title)
        for ln in lines:
            print("  ", ln)
 
# ---------- Nachbarschafts-Fächerung (ohne Anker/Interpolation) ----------

def _get_frame_value(state: Dict[str, Any], frame: int) -> int:
    return int(state.setdefault("frames", {}).get(str(frame), {}).get("count", 0))

def _set_frame_value(state: Dict[str, Any], frame: int, value: int) -> None:
    frames = state.setdefault("frames", {})
    entry, _created = _ensure_frame_entry(state, frame)
    entry["count"] = max(0, int(value))
    # Alt-Flags neutralisieren
    entry["anchor"] = False
    entry["interpolated"] = False
    frames[str(frame)] = entry

def _fan_out_neighbors(state: Dict[str, Any], center_frame: int, center_value: int) -> None:
    """
    Rollt den center_value gedämpft auf Nachbarn aus:
    f±1 := center_value-1, f±2 := center_value-2, ... bis >0.
    Konflikthandling: arithmetisches Mittel (kaufmännisch gerundet).
    """
    if center_value <= 1:
        return
    def _blend(old_v: int, new_v: int) -> int:
        if old_v <= 0:
            return new_v
        return int(round((old_v + new_v) / 2.0))

    # Beide Richtungen
    radius = center_value - 1
    for d in range(1, radius + 1):
        cand = center_value - d
        if cand <= 0:
            break
        for neighbor in (center_frame - d, center_frame + d):
            old = _get_frame_value(state, neighbor)
            _set_frame_value(state, neighbor, _blend(old, cand))


# ---------- Öffentliche API ----------

def orchestrate_on_jump(context: bpy.types.Context, frame: int) -> None:
    """
    Anker- & Interpolationsfreie Wiederholungslogik:
    - Erstbesuch: count := 1
    - Wiederbesuch: count := count + 1
    - Danach Dämpfungs-Fächerung auf Nachbarn (–1/–2/… bis >0), Konflikte werden gemittelt.
    - ABORT_AT bleibt als Obergrenze für count aktiv.
    """
    state = _get_state(context)
    entry, _created = _ensure_frame_entry(state, frame)
    # Zentrum hochzählen (oder initialisieren)
    center = int(entry.get("count", 0))
    center = 1 if center <= 0 else center + 1
    entry["count"] = center
    entry["anchor"] = False
    entry["interpolated"] = False

    # Abbruchschutz
    if center >= ABORT_AT:
        _set_triplet_mode_on_scene(context, None)
        _save_state(context, state)
        _popup_error_report(context, frame, entry)
        return

    # Nachbarn fächern
    _set_frame_value(state, frame, center)
    _fan_out_neighbors(state, frame, center)

    # Motion-Model/Triplet aus aktuellem count ableiten (unverändert)
    _apply_model_triplet_for_count(context, entry)
    _save_state(context, state)

def record_bidirectional_result(
    context: bpy.types.Context,
    frame: int,
    *,
    per_marker_frames: Dict[str, int],
    error_value_func: Callable[[bpy.types.MovieTrackingTrack], float],
) -> None:
    """Nach (Bi-)Directional Tracking aufrufen.
    A_k = Summe über alle Marker: frames_tracked(marker) * error_value(marker)
    k = aktuelle count des Frames (1..9). Bei >=10 wird nichts geschrieben (Abbruchfall).
    """
    state = _get_state(context)
    entry, _ = _ensure_frame_entry(state, frame)
    count = int(entry.get("count", 1))

    if count >= 10:
        # Abbruchfall: nur Report
        _save_state(context, state)
        _popup_error_report(context, frame, entry)
        return

    clip = context.edit_movieclip
    if not clip:
        return

    # Map: Track-Name -> Track
    tracks_by_name: Dict[str, bpy.types.MovieTrackingTrack] = {}
    for obj in clip.tracking.objects:
        for tr in obj.tracks:
            tracks_by_name[tr.name] = tr

    total = 0.0
    for name, frames_tracked in per_marker_frames.items():
        tr = tracks_by_name.get(name)
        if tr is None:
            continue
        try:
            err = float(error_value_func(tr))
        except Exception:
            err = 0.0
        total += float(frames_tracked) * err

    # A-Logging bleibt bewusst auf 1..9 gekappt: Auswahl-Logik nutzt A1..A5,
    # spätere Triplet-Schritte benötigen keine A>9.
    idx = max(1, min(count, 9))
    key = f"A{idx}"
    entry[key] = float(total)

    _save_state(context, state)

def reset_tracking_state(context: bpy.types.Context) -> None:
    """Setzt den gesamten Tracking-State (frames, counts, A-Werte) zurück."""
    try:
        state = {"frames": {}}
        _save_state(context, state)
        if "_tracking_triplet_mode" in context.scene:
            try:
                del context.scene["_tracking_triplet_mode"]
            except Exception:
                pass
    except Exception as exc:
        print(f"[tracking_state] Reset fehlgeschlagen: {exc}")
    return state

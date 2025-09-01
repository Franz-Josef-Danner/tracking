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

@dataclass
class FrameEntry:
    count: int = 1  # wie oft dieser Frame durchlaufen wurde (1..)
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


def _save_state(context: bpy.types.Context, state: Dict[str, Any]) -> None:
    context.scene[SCENE_STATE_PROP] = json.dumps(state, separators=(",", ":"))


def _ensure_frame_entry(state: Dict[str, Any], frame: int) -> Tuple[Dict[str, Any], bool]:
    frames = state.setdefault("frames", {})
    key = str(frame)
    if key not in frames:
        frames[key] = asdict(FrameEntry())
        return frames[key], True
    return frames[key], False


# ---------- Motion-Model / Triplet ----------

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


# ---------- Öffentliche API ----------

def orchestrate_on_jump(context: bpy.types.Context, frame: int) -> None:
    """Am Ende von jump_to_frame aufrufen.
    Regeln:
    - Frame erstmalig: count=1, Model=A1(Loc).
    - Bereits vorhanden: count += 1; setze Model gem. count.
    - count==6..9: bestes A1..A5 + Triplet 1..4 (nur Szene-Flag).
    - count==10: Abbruch + Error-Report (Popup) aus JSON, keine weiteren Änderungen.
    """
    state = _get_state(context)
    entry, created = _ensure_frame_entry(state, frame)

    if created:
        # Neu: count=1 → A1 ("Loc")
        _set_motion_model_for_all_selected_tracks(context, MOTION_MODEL_BY_COUNT[1])
        _set_triplet_mode_on_scene(context, None)
        _save_state(context, state)
        return

    # Wiederbesuch → count erhöhen
    entry["count"] = int(entry.get("count", 1)) + 1
    count = entry["count"]

    if count == 10:
        # Abbruchbedingung: Report zeigen und nichts mehr verstellen
        _save_state(context, state)
        _popup_error_report(context, frame, entry)
        return

    if 1 <= count <= 5:
        model = MOTION_MODEL_BY_COUNT[count]
        _set_motion_model_for_all_selected_tracks(context, model)
        _set_triplet_mode_on_scene(context, None)

    elif 6 <= count <= 9:
        best_model = _pick_best_model_from_A1_A5(entry)
        _set_motion_model_for_all_selected_tracks(context, best_model)
        _set_triplet_mode_on_scene(context, count - 5)  # 1..4

    else:
        # >10 ist durch return oben nicht erreichbar; falls doch, fix auf bestes Model + Triplet 4
        best_model = _pick_best_model_from_A1_A5(entry)
        _set_motion_model_for_all_selected_tracks(context, best_model)
        _set_triplet_mode_on_scene(context, 4)

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

    idx = max(1, min(count, 9))
    key = f"A{idx}"
    entry[key] = float(total)

    _save_state(context, state)
# Helper/marker_position_forward_calibration.py
# ---------------------------------------------------------------------
# Diagnose-Helper: Vergleicht Scene-Track-Strings mit aktuellen Tracks
# Gibt aus:
#   - welche Tracks im Scene-String stehen
#   - welche tatsächlich in der Szene existieren
#   - welche im String fehlen oder zusätzlich sind
# ---------------------------------------------------------------------

import bpy, ast
from typing import List, Tuple, Optional

# ------------------------------------------------------------
# Clip / Scene Utilities
# ------------------------------------------------------------

def _active_clip(context) -> Optional[bpy.types.MovieClip]:
    space = getattr(context, "space_data", None)
    clip_ui = getattr(space, "clip", None) if space else None
    clip_edit = getattr(context, "edit_movieclip", None)
    return clip_ui or clip_edit

# ------------------------------------------------------------
# Referenz-Namen aus Scene lesen
# ------------------------------------------------------------

def _select_reference_names(scene) -> Tuple[Optional[List[str]], str]:
    has_good = "good_tracks" in scene
    has_best = "best_tracks" in scene
    key = "good_tracks" if has_good else ("best_tracks" if has_best else None)
    if key is None:
        print("[MarkerCalib] ⚠️ Kein 'good_tracks' oder 'best_tracks' vorhanden.")
        return None, ""

    names_key = f"{key}_names"
    if names_key in scene:
        return list(scene[names_key]), key

    map_key = f"{key}_uuid_map"
    raw = list(scene[key])
    if map_key in scene:
        try:
            uuid_map = ast.literal_eval(scene[map_key])
            names = [uuid_map.get(u, u) for u in raw]
            return names, key
        except Exception:
            pass
    return raw, key

# ------------------------------------------------------------
# Haupt-Diagnosefunktion
# ------------------------------------------------------------

def correct_marker_positions(context, selected_tracks=None,
                             frame_a=None, frame_b=None, frame_c=None, frame_d=None):
    print("\n[MarkerCalib] ---- Diagnose: Scene-Strings vs. Scene-Tracks ----")

    scene = context.scene
    clip = _active_clip(context)
    if not clip:
        print("[MarkerCalib] ❌ Kein aktiver Clip gefunden.")
        return

    # --- Scene-String laden ---
    ref_names, key = _select_reference_names(scene)
    if not ref_names:
        print("[MarkerCalib] ❌ Kein Referenz-Set in Szene vorhanden.")
        return

    # --- Tracks im Clip ---
    scene_tracks = [t.name for t in clip.tracking.tracks if not t.mute]

    # --- Vergleiche ---
    ref_set = set(ref_names)
    scene_set = set(scene_tracks)

    only_in_ref = sorted(ref_set - scene_set)
    only_in_scene = sorted(scene_set - ref_set)
    in_both = sorted(ref_set & scene_set)

    print(f"[MarkerCalib] Aktiver Clip: {clip.name}")
    print(f"[MarkerCalib] Scene-Key: '{key}'  |  {len(ref_names)} gespeicherte Einträge")
    print(f"[MarkerCalib] Aktuelle Tracks im Clip: {len(scene_tracks)}")

    print("\n[MarkerCalib] --- Vergleich ---")
    print(f"Gemeinsam:   {len(in_both)}")
    print(f"Nur im String ({len(only_in_ref)}): {only_in_ref[:20]}")
    print(f"Nur in Szene ({len(only_in_scene)}): {only_in_scene[:20]}")

    print("\n[MarkerCalib] ---- Diagnose abgeschlossen ----\n")

# Operator/track_operator_backwards.py

import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_start_frame as sc_get_start_frame, get_end_frame


# ------------------------------------------------------------
# Hilfsfunktionen (identisch nutzbar für beide Richtungen)
# ------------------------------------------------------------

def _find_clip_editor_area(clip):
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "CLIP_EDITOR":
                for space in area.spaces:
                    if space.type == "CLIP_EDITOR":
                        if getattr(space, "clip", None) == clip or space.clip is None:
                            region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None


def _collect_selected_track_names(context) -> List[str]:
    """Liefert Namen aller aktuell selektierten Tracks."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return []
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return []
    return [t.name for t in tracking.tracks if getattr(t, "select", False)]


def _filter_active_tracks_at_frame(context, track_names: List[str], frame: int) -> Tuple[List[str], int]:
    """Prüft, welche der Tracks im angegebenen Frame noch aktiv (nicht gemutet, Marker vorhanden) sind."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return [], len(track_names)
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return [], len(track_names)

    remaining = []
    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue
        mk = tr.markers.find_frame(frame)
        if mk and not getattr(mk, "mute", False):
            remaining.append(name)

    dropped = len(track_names) - len(remaining)
    return remaining, dropped


# ------------------------------------------------------------
# Operator (UI Wrapper)
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle_backwards(bpy.types.Operator):
    """Trackt selektierte Marker frameweise rückwärts, stabiler Ablauf für Blender 4.4+."""
    bl_idname = "kaiserlich_tracker.track_cycle_backwards"
    bl_label = "Track Zyklus (Rückwärts, Frame für Frame)"
    bl_description = (
        "Trackt die aktuell selektierten Tracks frameweise rückwärts, "
        "bis kein Track mehr aktiv ist oder der Szenen-Start erreicht wurde."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    def execute(self, context):
        return track_cycle_backwards(context, max_frames=self.max_frames)


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


# ------------------------------------------------------------
# Hauptimplementierung: Tracking-Zyklus rückwärts
# ------------------------------------------------------------

def track_cycle_backwards(context, *, max_frames: int = 0):
    """Implementiert den stabilen Tracking-Zyklus (frameweise Tracking) rückwärts
    und setzt den Playhead am Ende auf die Ausgangsposition zurück.
    Zusätzlich bleiben ALLE ursprünglich getrackten Tracks selektiert."""
    start_frame_saved = ph_get_start_frame(context)

    try:
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            return {"CANCELLED"}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            return {"CANCELLED"}

        # Szenen-Grenzen strikt aus Helper/scene.py
        frame_start = sc_get_start_frame(context)
        frame_end   = get_end_frame(context)
        if frame_end < frame_start:
            frame_end = frame_start

        # Originale Selektion sichern (bleibt bestehen)
        original_selected: List[str] = _collect_selected_track_names(context)
        if not original_selected:
            return {"CANCELLED"}

        # Arbeitsliste unabhängig von Selektion pflegen
        processing_names: List[str] = list(original_selected)

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            return {"CANCELLED"}

        # Startposition rückwärts: nie über Szenenende hinaus starten,
        # und nie vor Szenenstart laufen. Playhead einklemmen.
        current_frame = int(scene.frame_current)
        if current_frame > frame_end:
            current_frame = frame_end
        if current_frame < frame_start:
            current_frame = frame_start

        # Ausgangsframe setzen
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        histories: Dict[str, Deque[Tuple[int, float, float]]] = {
            name: deque(maxlen=10) for name in processing_names
        }

        # Ursprüngliche Selektion fixieren
        for tr in tracking.tracks:
            if tr.name in original_selected:
                tr.select = True

        frames_processed = 0

        # --- Hauptloop (rückwärts) ---
        while True:
            if current_frame < frame_start:
                break
            if not processing_names:
                break
            if max_frames > 0 and frames_processed >= max_frames:
                break

            # Historie aktualisieren
            for name in list(processing_names):
                tr = tracking.tracks.get(name)
                if not tr:
                    continue
                mk = tr.markers.find_frame(current_frame)
                if mk:
                    histories[name].append((current_frame, mk.co[0], mk.co[1]))

            # Optionales Preprocessing
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception:
                pass

            # Tracking rückwärts
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                try:
                    bpy.ops.clip.track_markers(backwards=True, sequence=False)
                except Exception:
                    break

            # Step rückwärts & Clamp
            if space.clip_user.frame_current == current_frame:
                space.clip_user.frame_current -= 1

            if space.clip_user.frame_current < frame_start:
                space.clip_user.frame_current = frame_start

            scene.frame_current = space.clip_user.frame_current
            current_frame = space.clip_user.frame_current
            frames_processed += 1

            # Stop-Kriterium: Szenenstart erreicht
            if current_frame <= frame_start:
                break

            # Arbeitsliste pflegen (Selektion unberührt lassen)
            processing_names, _ = _filter_active_tracks_at_frame(context, processing_names, current_frame)

        # Vor Rückgabe: Originalselektion nochmals hartsetzen
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        return {"FINISHED"}

    finally:
        # Playhead robust zurücksetzen
        try:
            reset_to_frame(context, start_frame_saved)
        except Exception:
            pass

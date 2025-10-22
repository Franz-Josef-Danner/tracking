# Operator/track_operator.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_end_frame


# ------------------------------------------------------------
# Hilfsfunktionen
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
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Trackt selektierte Marker frameweise und prüft Playhead-Wechsel."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Frame für Frame)"
    bl_description = "Trackt Marker frameweise und prüft Playhead-Wechsel, bevor der nächste Schritt erfolgt."
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    def invoke(self, context, event):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        current_frame = int(scene.frame_current)
        last_frame = scene.get("kaiserlich_last_frame", None)

        # Prüfen, ob Frame gewechselt hat
        if last_frame == current_frame:
            print(f"[Kaiserlich Tracker] Frame unverändert ({current_frame}) – kein Tracking-Schritt ausgeführt.")
            return {'PASS_THROUGH'}
        else:
            print(f"[Kaiserlich Tracker] Frame-Wechsel erkannt: {last_frame} → {current_frame}")
            scene["kaiserlich_last_frame"] = current_frame

        # Wenn Frame gewechselt, Tracking-Schritt durchführen
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            return {"CANCELLED"}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            return {"CANCELLED"}

        start_frame = ph_get_start_frame(context)
        end_frame = get_end_frame(context)
        if end_frame < start_frame:
            end_frame = start_frame

        # Originalselektion sichern
        original_selected: List[str] = _collect_selected_track_names(context)
        if not original_selected:
            return {"CANCELLED"}

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            return {"CANCELLED"}

        current_frame = scene.frame_current
        processing_names: List[str] = list(original_selected)

        # --- Tracking Schritt ---
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            except Exception as e:
                print(f"[Kaiserlich Tracker][Fehler beim Tracking] {e}")
                return {"CANCELLED"}

        # --- Playhead prüfen / weiterbewegen ---
        if space.clip_user.frame_current == current_frame:
            space.clip_user.frame_current += 1

        # Clamp
        if space.clip_user.frame_current > end_frame:
            space.clip_user.frame_current = end_frame

        scene.frame_current = space.clip_user.frame_current

        # --- Fortschritt loggen ---
        print(f"[Kaiserlich Tracker] Tracking durchgeführt bis Frame {scene.frame_current}")

        # Selektion erhalten
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        return {"FINISHED"}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)

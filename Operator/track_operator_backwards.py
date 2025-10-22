# Operator/track_operator_backwards.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_start_frame as sc_get_start_frame, get_end_frame


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def _find_clip_editor_area(clip):
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
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
# Operator (rückwärts Tracking)
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle_backwards(bpy.types.Operator):
    """Trackt selektierte Marker frameweise rückwärts mit Playhead-Prüfung."""
    bl_idname = "kaiserlich_tracker.track_cycle_backwards"
    bl_label = "Track Zyklus (Rückwärts, Frame für Frame)"
    bl_description = (
        "Trackt selektierte Marker rückwärts und prüft, ob sich der Playhead verändert hat, "
        "bevor der nächste Schritt ausgeführt wird."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    # --------------------------------------------------------
    # Invoke: prüft Frame-Wechsel
    # --------------------------------------------------------
    def invoke(self, context, event):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'ERROR'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        current_frame = int(scene.frame_current)
        last_frame = scene.get("kaiserlich_last_frame_backwards", None)

        # Prüfen, ob Frame unverändert
        if last_frame == current_frame:
            print(f"[Kaiserlich Tracker][Backwards] Frame unverändert ({current_frame}) – kein Tracking-Schritt.")
            return {'PASS_THROUGH'}
        else:
            print(f"[Kaiserlich Tracker][Backwards] Frame-Wechsel erkannt: {last_frame} → {current_frame}")
            scene["kaiserlich_last_frame_backwards"] = current_frame

        # Wenn Frame gewechselt → execute()
        return self.execute(context)

    # --------------------------------------------------------
    # Execute: eigentlicher Tracking-Schritt rückwärts
    # --------------------------------------------------------
    def execute(self, context):
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            return {"CANCELLED"}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            return {"CANCELLED"}

        frame_start = sc_get_start_frame(context)
        frame_end = get_end_frame(context)
        if frame_end < frame_start:
            frame_end = frame_start

        original_selected: List[str] = _collect_selected_track_names(context)
        if not original_selected:
            return {"CANCELLED"}

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            return {"CANCELLED"}

        current_frame = int(scene.frame_current)
        if current_frame > frame_end:
            current_frame = frame_end
        if current_frame < frame_start:
            current_frame = frame_start

        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        processing_names: List[str] = list(original_selected)

        # --- Tracking-Schritt rückwärts ---
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
                bpy.ops.clip.track_markers(backwards=True, sequence=False)
            except Exception as e:
                print(f"[Kaiserlich Tracker][Backwards][Fehler] {e}")
                return {"CANCELLED"}

        # --- Frame zurücksetzen ---
        if space.clip_user.frame_current == current_frame:
            space.clip_user.frame_current -= 1

        if space.clip_user.frame_current < frame_start:
            space.clip_user.frame_current = frame_start

        scene.frame_current = space.clip_user.frame_current
        print(f"[Kaiserlich Tracker][Backwards] Tracking bis Frame {scene.frame_current}")

        # Selektion erhalten
        for tr in tracking.tracks:
            tr.select = (tr.name in original_selected)

        return {"FINISHED"}


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle_backwards)

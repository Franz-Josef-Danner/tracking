# Operator/track_operator_backwards.py

import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame, reset_to_frame


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
        return track_cycle_backwards(context, max_frames=self.max_frames, report_fn=self.report)


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


# ------------------------------------------------------------
# Hauptimplementierung: Tracking-Zyklus rückwärts
# ------------------------------------------------------------

def track_cycle_backwards(context, *, max_frames: int = 0, report_fn=None):
    """Implementiert den stabilen Tracking-Zyklus (frameweise Tracking) rückwärts
    und setzt den Playhead am Ende auf die Ausgangsposition zurück."""
    # Ausgangsposition robust sichern
    start_frame_saved = get_start_frame(context)

    try:
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            if report_fn:
                report_fn({"WARNING"}, "Kein aktiver Clip.")
            return {"CANCELLED"}

        tracking = getattr(clip, "tracking", None)
        if tracking is None:
            if report_fn:
                report_fn({"WARNING"}, "Clip hat kein Tracking-Objekt.")
            return {"CANCELLED"}

        frame_start = getattr(scene, "frame_start", None)
        if frame_start is None:
            if report_fn:
                report_fn({"WARNING"}, "Kein Szenen-Startframe gesetzt.")
            return {"CANCELLED"}

        # Startframe für den Trackinglauf aus dem Helper übernehmen
        current_frame = start_frame_saved

        track_names = _collect_selected_track_names(context)
        if not track_names:
            if report_fn:
                report_fn({"WARNING"}, "Keine selektierten Tracks.")
            return {"CANCELLED"}

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            if report_fn:
                report_fn({"WARNING"}, "Kein CLIP_EDITOR Kontext gefunden.")
            return {"CANCELLED"}

        # Ausgangsframe in Szene und Clip-User setzen
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        # Historien (optional, analog zur Vorwärtsvariante)
        histories: Dict[str, Deque[Tuple[int, float, float]]] = {
            name: deque(maxlen=10) for name in track_names
        }

        # Tracks korrekt selektieren
        for tr in tracking.tracks:
            tr.select = tr.name in track_names

        frames_processed = 0
        failures_total = 0

        # --- Hauptloop (rückwärts) ---
        while True:
            if current_frame < frame_start:
                break
            if not track_names:
                break
            if max_frames > 0 and frames_processed >= max_frames:
                break

            # Markerhistorie aktualisieren
            for name in list(track_names):
                tr = tracking.tracks.get(name)
                if not tr:
                    continue
                mk = tr.markers.find_frame(current_frame)
                if mk:
                    histories[name].append((current_frame, mk.co[0], mk.co[1]))

            # Optionales Preprocessing (Formeln, Stabilisierung, etc.)
            try:
                apply_formula_on_selected_tracks(context, max_frames=5)
            except Exception:
                # Silent-Fail analog Vorwärtsoperator
                pass

            # Blender Tracking Operator (rückwärts)
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                try:
                    bpy.ops.clip.track_markers(backwards=True, sequence=False)
                except Exception:
                    break

            # Frame-Dekrement (failsafe, falls Blender nicht gesprungen ist)
            if space.clip_user.frame_current == current_frame:
                space.clip_user.frame_current -= 1
            scene.frame_current = space.clip_user.frame_current
            current_frame = space.clip_user.frame_current
            frames_processed += 1

            # Aktive Tracks im neuen Frame prüfen
            track_names, dropped = _filter_active_tracks_at_frame(context, track_names, current_frame)
            if dropped:
                failures_total += dropped

            # Selektion updaten
            for tr in tracking.tracks:
                tr.select = tr.name in track_names

        # Still: keine Logs, nur Status
        return {"FINISHED"}

    finally:
        # Immer auf Ausgangsposition zurücksetzen – robust ggü. Fehlern/Cancel
        try:
            reset_to_frame(context, start_frame_saved)
        except Exception:
            # Silent fail: Die Rücksetzung soll nie den Operator hart failen lassen
            pass

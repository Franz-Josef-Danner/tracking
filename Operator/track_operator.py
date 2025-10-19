import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque
from ..Helper.formula_helper import apply_formula_on_selected_tracks


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
# Operator (Optional UI Wrapper)
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Trackt selektierte Marker frameweise, stabiler Ablauf für Blender 4.4+."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Frame für Frame)"
    bl_description = (
        "Trackt die aktuell selektierten Tracks frameweise vorwärts, "
        "bis kein Track mehr aktiv ist oder das Szenen-Ende erreicht wurde."
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
        return track_cycle(context, max_frames=self.max_frames, report_fn=self.report)


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)


# ------------------------------------------------------------
# Hauptimplementierung: Tracking-Zyklus
# ------------------------------------------------------------

def track_cycle(context, *, max_frames: int = 0, report_fn=None):
    """Implementiert den stabilen Tracking-Zyklus (frameweise Tracking)."""
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

    end_frame = getattr(scene, "frame_end", None)
    if end_frame is None:
        if report_fn:
            report_fn({"WARNING"}, "Kein Szenen-Endframe gesetzt.")
        return {"CANCELLED"}

    start_frame = scene.frame_current
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

    current_frame = start_frame
    space.clip_user.frame_current = current_frame
    scene.frame_current = current_frame

    histories: Dict[str, Deque[Tuple[int, float, float]]] = {
        name: deque(maxlen=10) for name in track_names
    }

    # Tracks korrekt selektieren
    for tr in tracking.tracks:
        tr.select = tr.name in track_names

    frames_processed = 0
    failures_total = 0

    # --- Hauptloop ---
    while True:
        if current_frame > end_frame:
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
            pass

        # Blender Tracking Operator ausführen
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            try:
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            except Exception:
                break

        # Frame-Inkrement
        if space.clip_user.frame_current == current_frame:
            space.clip_user.frame_current += 1
        scene.frame_current = space.clip_user.frame_current
        current_frame = space.clip_user.frame_current
        frames_processed += 1

        # Aktive Tracks prüfen
        track_names, dropped = _filter_active_tracks_at_frame(context, track_names, current_frame)
        if dropped:
            failures_total += dropped

        # Selektion updaten
        for tr in tracking.tracks:
            tr.select = tr.name in track_names

    # Kein Logging, nur stilles Return
    return {"FINISHED"}

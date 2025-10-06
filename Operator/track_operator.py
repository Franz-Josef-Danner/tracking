import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from Helper.motionmodel import evaluate_motion_model


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def _find_clip_editor_area(clip):
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        if getattr(space, 'clip', None) == clip or space.clip is None:
                            region_window = next((r for r in area.regions if r.type == 'WINDOW'), None)
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None


def _collect_selected_track_names(context) -> List[str]:
    clip = getattr(context.space_data, 'clip', None)
    if clip is None:
        return []
    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        return []
    return [t.name for t in tracking.tracks if getattr(t, 'select', False)]


def _filter_active_tracks_at_frame(context, track_names: List[str], frame: int) -> Tuple[List[str], int]:
    """Prüft, welche der benannten Tracks im angegebenen Frame einen Marker besitzen."""
    clip = getattr(context.space_data, 'clip', None)
    if clip is None:
        return [], len(track_names)
    tracking = getattr(clip, 'tracking', None)
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
    """Trackt selektierte Marker frameweise, stabiler Ablauf für Blender 4.4+."""
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Frame für Frame)"
    bl_description = (
        "Trackt die aktuell selektierten Tracks frameweise vorwärts, "
        "bis kein Track mehr aktiv ist oder das Szenen-Ende erreicht wurde."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames = bpy.props.IntProperty(
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    verbose = bpy.props.BoolProperty(
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole"
    )

    def _log(self, *msg):
        if self.verbose:
            print("[Kaiserlich Tracker][Track]", *msg)

    # --------------------------------------------------------

    def execute(self, context):
        # Delegiert an die freistehende track_cycle Funktion unten, um Logik testbar zu halten.
        result = track_cycle(context, max_frames=self.max_frames, verbose=self.verbose, report_fn=self.report)
        return result
        # Alte Logik wurde in track_cycle ausgelagert.
        return {'FINISHED'}  # Fallback (sollte nie erreicht werden)


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)


if __name__ == "__main__":
    register()


# ---------------------------------------------------------------------------
# Freistehende Track-Cycle Implementierung (funktionsorientiert)
# ---------------------------------------------------------------------------

def track_cycle(context, *, max_frames: int = 0, verbose: bool = True, report_fn=None):
    """Implementiert den in der Spezifikation beschriebenen Tracking-Zyklus.

    Schritte:
        INIT scene, clip, tracking
        Validierungen – bei Fehler → CANCELLED
        Start-/End-Frames ermitteln
        Selektierte Tracks sammeln
        Clip-Editor-Kontext finden für Override
        Schleife: frameweise track_markers aufrufen
            - Bewegungsmodell aus letzten N (≤10) Frames jedes aktiven Tracks evaluieren
            - Abbruchbedingungen prüfen
            - verlorene Tracks entfernen
    """
    def _log(*a):
        if verbose:
            print("[Kaiserlich Tracker][Cycle]", *a)

    scene = context.scene
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        if report_fn:
            report_fn({'WARNING'}, "Kein aktiver Clip.")
        return {'CANCELLED'}

    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        if report_fn:
            report_fn({'WARNING'}, "Clip hat kein Tracking-Objekt.")
        return {'CANCELLED'}

    end_frame = getattr(scene, 'frame_end', None)
    if end_frame is None:
        if report_fn:
            report_fn({'WARNING'}, "Kein Szenen-Endframe gesetzt.")
        return {'CANCELLED'}

    start_frame = scene.frame_current
    track_names = _collect_selected_track_names(context)
    if not track_names:
        if report_fn:
            report_fn({'WARNING'}, "Keine selektierten Tracks.")
        return {'CANCELLED'}

    window, area, region, space = _find_clip_editor_area(clip)
    if not window:
        if report_fn:
            report_fn({'WARNING'}, "Kein CLIP_EDITOR Kontext gefunden.")
        return {'CANCELLED'}

    # Kontext initialisieren
    current_frame = start_frame
    space.clip_user.frame_current = current_frame
    scene.frame_current = current_frame

    # Historie der letzten <=10 Frames für jeden Track
    histories: Dict[str, Deque[Tuple[int, float, float]]] = {
        name: deque(maxlen=10) for name in track_names
    }

    _log("Start Tracking-Zyklus", f"Start={start_frame}", f"End={end_frame}", f"Tracks={len(track_names)}")

    # Nur selektierte markieren
    for tr in tracking.tracks:
        tr.select = tr.name in track_names

    frames_processed = 0
    failures_total = 0

    while True:
        if current_frame > end_frame:
            _log("End-Frame erreicht → Ende")
            break
        if not track_names:
            _log("Keine aktiven Tracks mehr → Ende")
            break
        if max_frames > 0 and frames_processed >= max_frames:
            _log("Max Frames erreicht → Ende")
            break

        _log(f"Track Step @Frame {current_frame} (Aktive: {len(track_names)})")

        # Bewegungsmodell vorbereiten: vorhandene Marker-Positionen einsammeln
        for name in list(track_names):
            tr = tracking.tracks.get(name)
            if not tr:
                continue
            mk = tr.markers.find_frame(current_frame)
            if mk:
                histories[name].append((current_frame, mk.co[0], mk.co[1]))

        # Beispiel-Auswertung (optional): Modellklassifikation pro Track
        for name, hist in histories.items():
            if len(hist) >= 2:
                model = evaluate_motion_model(list(hist))
                # (Derzeit nur Log – spätere Nutzung für adaptive Strategien möglich)
                _log(f"  Modell {name}: {model}")

        # Tracking-Schritt ausführen
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            try:
                bpy.ops.clip.track_markers(backwards=False, sequence=False)
            except Exception as e:
                _log("Fehler beim track_markers", e)
                break

        # Frame Synchronisation
        if space.clip_user.frame_current == current_frame:
            space.clip_user.frame_current += 1
        scene.frame_current = space.clip_user.frame_current
        current_frame = space.clip_user.frame_current
        frames_processed += 1

        # Aktive Tracks nach neuem Frame prüfen
        track_names, dropped = _filter_active_tracks_at_frame(context, track_names, current_frame)
        if dropped:
            failures_total += dropped
            _log(f"Verlorene Tracks: {dropped} (verbleibend {len(track_names)})")

        # Selektion aktualisieren
        for tr in tracking.tracks:
            tr.select = tr.name in track_names

    summary = (
        f"Start={start_frame} Ende={current_frame} "
        f"Schritte={frames_processed} Aktiv={len(track_names)} Verloren={failures_total}"
    )
    _log("Tracking beendet", summary)
    if report_fn:
        report_fn({'INFO'}, f"Track-Zyklus: {summary}")
    return {'FINISHED'}


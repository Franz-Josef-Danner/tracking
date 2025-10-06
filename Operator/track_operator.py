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
        scene = context.scene
        clip = getattr(context.space_data, "clip", None)
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip.")
            return {'CANCELLED'}

        tracking = getattr(clip, 'tracking', None)
        if tracking is None:
            self.report({'WARNING'}, "Clip hat kein Tracking-Objekt.")
            return {'CANCELLED'}

        end_frame_scene = getattr(scene, "frame_end", None)
        if end_frame_scene is None:
            self.report({'WARNING'}, "Kein Szenen-Endframe gesetzt.")
            return {'CANCELLED'}

        start_frame = scene.frame_current
        track_names = _collect_selected_track_names(context)
        if not track_names:
            self.report({'WARNING'}, "Keine selektierten Tracks.")
            return {'CANCELLED'}

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            self.report({'WARNING'}, "Kein CLIP_EDITOR Kontext gefunden.")
            return {'CANCELLED'}

        # Start-Setup
        frames_processed = 0
        failures_total = 0
        current_frame = start_frame

        # Szene & Clip synchronisieren
        space.clip_user.frame_current = current_frame
        scene.frame_current = current_frame

        self._log("Start:", f"Frame={start_frame}", f"End={end_frame_scene}", f"Tracks={len(track_names)}")

        # Nur selektierte Tracks aktiv halten
        for tr in tracking.tracks:
            tr.select = tr.name in track_names

        # Historien für Motion Model
        histories: Dict[str, Deque[Tuple[int, float, float]]] = {name: deque(maxlen=10) for name in track_names}
        # Initiale Positionen (Startframe)
        for name in track_names:
            tr = tracking.tracks.get(name)
            if tr:
                mk = tr.markers.find_frame(current_frame)
                if mk:
                    histories[name].append((current_frame, mk.co[0], mk.co[1]))

        # Hauptschleife
        while True:
            if self.max_frames > 0 and frames_processed >= self.max_frames:
                self._log("Limit erreicht → Abbruch")
                break
            if current_frame >= end_frame_scene:
                self._log("Szenen-Ende erreicht → Abbruch")
                break
            if not track_names:
                self._log("Keine aktiven Tracks mehr → Abbruch")
                break

            self._log(f"→ Frame {current_frame}: Tracking {len(track_names)} Tracks")

            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                try:
                    bpy.ops.clip.track_markers(backwards=False, sequence=False)
                except Exception as e:
                    self._log(f"Fehler beim track_markers: {e}")
                    break

            # Sicherstellen, dass Clip wirklich einen Frame weiterspringt
            prev_frame = current_frame
            next_frame = space.clip_user.frame_current
            if next_frame == prev_frame:
                next_frame = prev_frame + 1
                space.clip_user.frame_current = next_frame

            # Szene aktualisieren (nur visuell, nicht zwingend nötig)
            scene.frame_current = space.clip_user.frame_current
            current_frame = next_frame
            frames_processed += 1

            # Neue Marker-Positionen diesem Frame erfassen
            for name in track_names:
                tr = tracking.tracks.get(name)
                if not tr:
                    continue
                mk = tr.markers.find_frame(current_frame)
                if mk:
                    histories[name].append((current_frame, mk.co[0], mk.co[1]))

            # Motion-Model evaluieren (nur Log, keine Steuerung)
            for name, hist in histories.items():
                if len(hist) >= 2:
                    model = evaluate_motion_model(list(hist))
                    self._log(f"  Modell {name}: {model}")

            # Filtere verlorene Tracks
            track_names, dropped = _filter_active_tracks_at_frame(context, track_names, current_frame)
            failures_total += dropped
            if dropped > 0:
                self._log(f"Tracks verloren: {dropped}, aktiv: {len(track_names)}")

            # Nur verbleibende Tracks selektieren
            for tr in tracking.tracks:
                tr.select = tr.name in track_names

        summary = (
            f"Start={start_frame} Ende={current_frame} "
            f"Schritte={frames_processed} Aktiv={len(track_names)} "
            f"Ausgefallen={failures_total}"
        )
        self._log("Fertig:", summary)
        self.report({'INFO'}, f"Track-Zyklus beendet: {summary}")
        return {'FINISHED'}


# ------------------------------------------------------------
# Registrierung
# ------------------------------------------------------------

def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle)


if __name__ == "__main__":
    register()


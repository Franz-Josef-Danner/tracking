import bpy
from typing import List, Tuple


def _find_clip_editor_area(clip):
    """Sucht eine CLIP_EDITOR Area für Context Override (ähnlich wie in delete.py)."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'CLIP_EDITOR':
                for space in area.spaces:
                    if space.type == 'CLIP_EDITOR':
                        if getattr(space, 'clip', None) == clip or space.clip is None:
                            region_window = None
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    region_window = region
                                    break
                            if region_window:
                                return window, area, region_window, space
    return None, None, None, None


def _collect_selected_track_names(context) -> List[str]:
    clip = context.space_data.clip if getattr(context, 'space_data', None) else None
    if clip is None:
        return []
    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        return []
    names = [t.name for t in tracking.tracks if getattr(t, 'select', False)]
    return names


def _filter_active_tracks_at_frame(context, track_names: List[str], frame: int) -> Tuple[List[str], int]:
    """Prüft welche der benannten Tracks im angegebenen Frame einen Marker besitzen.

    Rückgabe: (aktive_namen, anzahl_weggefallen)
    """
    clip = context.space_data.clip if getattr(context, 'space_data', None) else None
    if clip is None:
        return [], len(track_names)
    tracking = getattr(clip, 'tracking', None)
    if tracking is None:
        return [], len(track_names)

    remaining = []
    for name in track_names:
        tr = tracking.tracks.get(name)
        if tr is None:
            continue
        mk = tr.markers.find_frame(frame)
        if mk is None or getattr(mk, 'mute', False):
            # Track hat in diesem Frame keinen gültigen Marker -> raus
            continue
        remaining.append(name)
    dropped = len(track_names) - len(remaining)
    return remaining, dropped


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Zyklus (Frame für Frame)"
    bl_description = (
        "Trackt die aktuell selektierten Tracks frameweise vorwärts, bis entweder kein Track mehr aktiv ist oder das Szenen-Ende erreicht wurde."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(  # type: ignore
        name="Max Frames",
        description="Optionale Sicherheitsbegrenzung der Schritte (0 = kein Limit)",
        default=0,
        min=0,
        soft_max=100000,
    )

    verbose: bpy.props.BoolProperty(  # type: ignore
        name="Verbose Log",
        default=True,
        description="Ausführliches Logging in der Konsole"
    )

    def _log(self, *msg):  # kleine Hilfsfunktion
        if self.verbose:
            print("[Kaiserlich Tracker][Track]", *msg)

    def execute(self, context):  # noqa: C901 (bewusst etwas ausführlicher für klare Ablauflogik)
        scene = context.scene
        clip = context.space_data.clip if getattr(context, 'space_data', None) else None
        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Movie Clip Editor.")
            return {'CANCELLED'}
        tracking = getattr(clip, 'tracking', None)
        if tracking is None:
            self.report({'WARNING'}, "Clip besitzt kein tracking Objekt.")
            return {'CANCELLED'}

        end_frame_scene = getattr(scene, 'frame_end', None)
        if end_frame_scene is None:
            self.report({'WARNING'}, "Szenen-Endframe unbekannt.")
            return {'CANCELLED'}

        start_frame = scene.frame_current
        track_names = _collect_selected_track_names(context)
        if not track_names:
            self.report({'WARNING'}, "Keine selektierten Tracks zum Start.")
            return {'CANCELLED'}

        self._log("Start Track Zyklus:", f"start_frame={start_frame}", f"scene_end={end_frame_scene}")
        self._log("Selektierte Tracks:", track_names)

        window, area, region, space = _find_clip_editor_area(clip)
        if not window:
            self.report({'WARNING'}, "Kein CLIP_EDITOR Kontext (Fenster) gefunden. Bitte Clip Editor öffnen.")
            return {'CANCELLED'}

        frames_processed = 0
        failures_total = 0
        last_report_frame = start_frame
        current_frame = start_frame

        # Zunächst sicherstellen, dass nur unsere gewünschten Tracks selektiert bleiben
        for tr in tracking.tracks:
            try:
                tr.select = tr.name in track_names
            except Exception:
                pass

        # Hauptschleife Frame für Frame
        while True:
            if self.max_frames > 0 and frames_processed >= self.max_frames:
                self._log("Max Frames Limit erreicht -> Abbruch")
                break

            if current_frame >= end_frame_scene:
                self._log("Szenen-Ende erreicht -> Abbruch")
                break

            if not track_names:
                self._log("Keine aktiven Tracks mehr -> Abbruch")
                break

            # Tracking-Schritt (ein Frame) ausführen
            self._log(f"Frame {current_frame} -> Tracking Step (Tracks={len(track_names)})")
            prev_frame = scene.frame_current
            with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                try:
                    bpy.ops.clip.track_markers(backwards=False, sequence=False)
                except Exception as e:  # noqa
                    self._log(f"Fehler beim track_markers: {e}")
                    break

            # Blender sollte (sequence=False) genau einen Schritt vor gehen. Prüfen.
            if scene.frame_current == prev_frame:
                # Kein automatischer Frame-Vorschub: wir erhöhen manuell.
                scene.frame_current = prev_frame + 1
            # Aktuellen Frame synchronisieren
            current_frame = scene.frame_current
            frames_processed += 1

            # Aktive (erfolgreiche) Tracks in diesem neuen Frame ermitteln
            track_names, dropped = _filter_active_tracks_at_frame(context, track_names, current_frame)
            failures_total += dropped
            if dropped > 0:
                self._log(f"Tracks weggefallen: {dropped} | Verbleibend: {len(track_names)}")

            # Optional regelmäßiges Fortschritts-Logging (alle 25 Frames)
            if self.verbose and (current_frame - last_report_frame) >= 25:
                self._log(f"Fortschritt: frame={current_frame} aktive_tracks={len(track_names)} (bisher weggefallen={failures_total})")
                last_report_frame = current_frame

        summary = (
            f"Start={start_frame} Ende={scene.frame_current} Schritte={frames_processed} "
            f"Aktive_Rest={len(track_names)} Ausgefallen={failures_total}"
        )
        self.report({'INFO'}, f"Track Zyklus fertig: {summary}")
        self._log("Fertig.", summary)
        return {'FINISHED'}

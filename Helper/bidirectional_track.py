# Helper/bidirectional_track.py
# PEP 8-konformes Hilfsskript für Blender, um selektierte Tracking-Marker
# frameweise vorwärts zu tracken, bis kein Track mehr Fortschritt macht.
#
# Nutzung:
#   - Öffne einen Movie Clip im CLIP_EDITOR.
#   - Wähle die gewünschten Tracks.
#   - Führe den Operator "helper.track_selected_forward_until_done" aus
#     (Suche in der Operator Search: F3).
#
# Optional: Import und direkter Funktionsaufruf:
#   from Helper import bidirectional_track
#   bidirectional_track.track_selected_forward_until_done()

import bpy
from typing import Iterable, Optional, Tuple


def _find_clip_context() -> Tuple[Optional[bpy.types.Area],
                                  Optional[bpy.types.Region],
                                  Optional[bpy.types.SpaceClip]]:
    """Suche einen CLIP_EDITOR samt UI-Region und SpaceClip.

    Returns:
        (area, region, space) oder (None, None, None), falls nicht gefunden.
    """
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            # Bevorzugt die 'WINDOW'-Region (Hauptansicht)
            window_region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, "spaces") else None
            if getattr(space, "type", None) == 'CLIP_EDITOR' and window_region:
                return area, window_region, space
    return None, None, None


def _get_active_clip(space: Optional[bpy.types.SpaceClip]) -> Optional[bpy.types.MovieClip]:
    """Gibt das aktive MovieClip des SpaceClip zurück, falls vorhanden."""
    if space and getattr(space, "clip", None):
        return space.clip
    # Fallback: Erstes MovieClip im Blend-File (nur wenn sinnvoll)
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def _selected_tracks(clip: bpy.types.MovieClip) -> Iterable[bpy.types.MovieTrackingTrack]:
    """Liefert alle selektierten Tracks des Clips (nicht gemutet, nicht disabled)."""
    if not clip:
        return []
    tracks = clip.tracking.tracks
    return [t for t in tracks if t.select and not t.mute and not t.disabled]


def _has_marker_at(track: bpy.types.MovieTrackingTrack, frame: int) -> bool:
    """Prüft, ob ein Marker für den Track an 'frame' existiert."""
    # MovieTrackingMarkers.find_frame(frame) -> Marker oder None
    try:
        return track.markers.find_frame(frame) is not None
    except Exception:
        # Defensive: alte Blender-Versionen oder unerwartete API-Änderung
        return any(m.frame == frame for m in track.markers)


def _can_attempt_step(track: bpy.types.MovieTrackingTrack,
                      clip: bpy.types.MovieClip,
                      current_frame: int) -> bool:
    """Heuristik: Darf/soll dieser Track im nächsten Schritt getrackt werden?"""
    if track.mute or track.disabled:
        return False
    # Es muss ein Marker am aktuellen Frame existieren, sonst kann der Operator
    # für diesen Track nicht sinnvoll fortsetzen.
    if not _has_marker_at(track, current_frame):
        return False
    # Clip-Grenzen beachten
    next_frame = current_frame + 1
    end_frame = getattr(clip, "frame_end", None)
    if end_frame is not None and next_frame > end_frame:
        return False
    return True


def track_selected_forward_until_done() -> int:
    """Trackt selektierte Marker frameweise vorwärts, bis kein Fortschritt mehr möglich ist.

    Ablauf:
      - Sucht einen CLIP_EDITOR-Kontext.
      - Ermittelt selektierte, gültige Tracks mit Marker im aktuellen Frame.
      - Führt pro Iteration genau EINEN Vorwärts-Track-Schritt aus (sequence=False).
      - Bricht ab, wenn in einer Iteration kein Track einen neuen Marker im (aktuellen+1)-Frame erzeugt hat.

    Returns:
      Anzahl der tatsächlich durchgeführten Vorwärts-Schritte (Frames).
    Raises:
      RuntimeError: wenn kein CLIP_EDITOR gefunden oder kein gültiger Clip/Track verfügbar ist.
    """
    area, region, space = _find_clip_context()
    if not all([area, region, space]):
        raise RuntimeError(
            "Kein CLIP_EDITOR mit gültiger WINDOW-Region gefunden. "
            "Bitte öffne einen Movie Clip im Movie Clip Editor und versuche es erneut."
        )

    clip = _get_active_clip(space)
    if not clip:
        raise RuntimeError("Kein aktives Movie Clip gefunden.")

    scene = bpy.context.scene
    step_count = 0

    while True:
        current_frame = scene.frame_current
        next_frame = current_frame + 1

        tracks = list(_selected_tracks(clip))
        if not tracks:
            # Nichts mehr selektiert oder alles stumm/disabled
            break

        # Prüfe, ob überhaupt irgendein selektierter Track einen Versuch wert ist
        if not any(_can_attempt_step(t, clip, current_frame) for t in tracks):
            break

        # Vor dem Schritt merken, welche Tracks schon einen Marker im next_frame haben
        had_marker_next = {t.name: _has_marker_at(t, next_frame) for t in tracks}

        # Operator im passenden Kontext ausführen: exakt 1 Frame (sequence=False)
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.track_markers(backwards=False, sequence=False)

        # Fortschritt messen: hat mindestens ein Track jetzt neu einen Marker im next_frame?
        progressed = False
        for t in tracks:
            has_now = _has_marker_at(t, next_frame)
            if has_now and not had_marker_next.get(t.name, False):
                progressed = True
                # keine break; wir zählen lediglich ob es IRGENDEINEN Fortschritt gab

        if not progressed:
            # Niemand kam im next_frame an -> Abbruch
            break

        # Szene auf den nächsten Frame bewegen, um dem UX von "Schritt für Schritt" zu entsprechen
        scene.frame_set(next_frame)
        step_count += 1

    return step_count


# ---------- Optionaler Blender-Operator für die UI/Operator Search ----------

class HELPER_OT_track_selected_forward_until_done(bpy.types.Operator):
    """Trackt selektierte Marker immer 1 Frame vorwärts, bis kein Fortschritt mehr möglich ist."""
    bl_idname = "clip.bidirectional_track"   # <<< WICHTIG: so wie Coordinator ihn aufruft
    bl_label = "Bidirectional Track (stepwise forward)"
    bl_options = {'REGISTER', 'UNDO'}

    # Falls du die Argumente aus tracking_coordinator übernehmen willst:
    use_cooperative_triplets: bpy.props.BoolProperty(
        name="Use Cooperative Triplets",
        default=False,
    )
    auto_enable_from_selection: bpy.props.BoolProperty(
        name="Auto Enable from Selection",
        default=False,
    )

    def execute(self, context):
        try:
            steps = track_selected_forward_until_done()
            self.report({'INFO'}, f"Tracking beendet. Schritte: {steps}")
            # Damit Coordinator weiterkommt:
            context.scene["bidi_active"] = False
            context.scene["bidi_result"] = "FINISHED"
            return {'FINISHED'}
        except RuntimeError as err:
            self.report({'ERROR'}, str(err))
            context.scene["bidi_active"] = False
            context.scene["bidi_result"] = "FAILED"
            return {'CANCELLED'}



# ---------- Register/Unregister ----------

def register():
    bpy.utils.register_class(HELPER_OT_track_selected_forward_until_done)


def unregister():
    bpy.utils.unregister_class(HELPER_OT_track_selected_forward_until_done)


# Erlaubt Testen via "Run Script"
if __name__ == "__main__":
    register()
